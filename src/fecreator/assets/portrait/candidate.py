from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fecreator.assets.portrait.manifest import GREEN_BG
from fecreator.assets.portrait.workflows import PreparedPortrait
from fecreator.contracts.diagnostics import Diagnostic, has_errors
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import Artifact
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import _fsync_directory
from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.imaging.io import save_indexed_png
from fecreator.imaging.quantize import map_to_palette, quantize_median_cut
from fecreator.imaging.resize import ResizeMode, resize
from fecreator.jobs.candidates import CandidateStore
from fecreator.lineage.store import LineageStore
from fecreator.references.model import ReferencePack
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BACKGROUND_ZONES,
    SAFE_ZONES,
    SHEET_H,
    SHEET_W,
    SLOTS,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import snap_gba_5bit, write_jasc
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

_BY_NAME = {slot.name: slot for slot in SLOTS}
_MAIN_SLOT = _BY_NAME["main"]
_UPPER_CONTENT, _LOWER_CONTENT = SAFE_ZONES
_EYE_SLOTS = ("half_closed_eyes", "closed_eyes")
_MOUTH_SLOTS = ("mouth1", "mouth2", "mouth3", "mouth4_status", "mouth5", "mouth6", "mouth7")
_CANDIDATE_STAGE_PREFIX = ".candidate-stage-"


class CandidateValidationError(Exception):
    """The assembled candidate does not satisfy the target specification."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__("candidate package validation failed")
        self.diagnostics = diagnostics


@dataclass
class CandidatePublication:
    snapshot: CandidateSnapshot
    lineage: LineageNode
    staged_root: Path
    candidate_published: bool = field(init=False, default=False)
    lineage_published: bool = field(init=False, default=False)

    def publish(self, workspace: Path) -> None:
        publish_candidate_atomically(workspace, self.snapshot, self.lineage, self.staged_root)
        self.candidate_published = True
        self.lineage_published = True

    def rollback(self, workspace: Path) -> None:
        rollback_candidate_publication(
            workspace,
            self.lineage.asset_id,
            self.staged_root,
            candidate_published=self.candidate_published,
            lineage_published=self.lineage_published,
        )


def prepare_candidate(
    *,
    ctx: PipelineContext,
    manifest: Manifest,
    prepared: PreparedPortrait,
    reference_pack: ReferencePack | None,
) -> CandidatePublication:
    staged_root = safe_join(ctx.workspace, f"{_CANDIDATE_STAGE_PREFIX}{uuid.uuid4().hex}")
    package_dir = safe_join(staged_root, "package")
    try:
        export_candidate_package(
            package_dir,
            prepared.sheet_rgb,
            GREEN_BG,
            approved_indices=prepared.approved_indices,
            approved_palette=prepared.approved_palette,
            edited_mask=prepared.edited_mask,
        )
        diagnostics = tuple(FeGbaPortraitStandard().validate(package_dir))
        if has_errors(diagnostics):
            raise CandidateValidationError(diagnostics)
        artifacts = candidate_artifacts(ctx.workspace, package_dir)
        lineage = candidate_lineage(
            job_id=ctx.job_id,
            manifest=manifest,
            prepared=prepared,
            reference_pack=reference_pack,
            artifacts=artifacts,
        )
        snapshot = CandidateSnapshot(
            job_id=ctx.job_id,
            lineage_id=lineage.asset_id,
            artifacts=artifacts,
            diagnostics=prepared.diagnostics + diagnostics,
            metrics=prepared.metrics,
            created_at=lineage.created_at,
        )
        return CandidatePublication(snapshot, lineage, staged_root)
    except Exception as exc:
        try:
            _remove_tree(staged_root)
        except Exception as cleanup_exc:
            raise cleanup_exc from exc
        raise


def assemble_candidate_sheet(main_rgb: np.ndarray, bg_rgb: tuple[int, int, int]) -> np.ndarray:
    if tuple(main_rgb.shape) != (_MAIN_SLOT.h, _MAIN_SLOT.w, 3):
        raise ValueError(
            f"main_rgb must be {_MAIN_SLOT.h}x{_MAIN_SLOT.w} RGB, got {main_rgb.shape}"
        )
    canvas = np.full((SHEET_H, SHEET_W, 3), bg_rgb, dtype=np.uint8)
    canvas[_slot_slice("main")] = main_rgb
    upper = _crop(
        main_rgb,
        _UPPER_CONTENT.x,
        _UPPER_CONTENT.y,
        _UPPER_CONTENT.w,
        _UPPER_CONTENT.h,
    )
    lower = _crop(
        main_rgb,
        _LOWER_CONTENT.x,
        _LOWER_CONTENT.y,
        _LOWER_CONTENT.w,
        _LOWER_CONTENT.h,
    )
    canvas[_slot_slice("mini")] = _render_slot(main_rgb, "mini")
    for name in _EYE_SLOTS:
        canvas[_slot_slice(name)] = _render_slot(upper, name)
    for name in _MOUTH_SLOTS:
        canvas[_slot_slice(name)] = _render_slot(lower, name)
    for zone in BACKGROUND_ZONES:
        canvas[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w] = bg_rgb
    return canvas


def export_candidate_package(
    package_dir: Path,
    sheet_rgb: np.ndarray,
    bg_rgb: tuple[int, int, int],
    *,
    approved_indices: np.ndarray | None = None,
    approved_palette: np.ndarray | None = None,
    edited_mask: np.ndarray | None = None,
) -> Path:
    if any(value is not None for value in (approved_indices, approved_palette, edited_mask)):
        if approved_indices is None or approved_palette is None or edited_mask is None:
            raise ValueError("approved indices, palette, and edit mask must be supplied together")
        indices, palette = _preserve_approved_palette(
            sheet_rgb,
            approved_indices,
            approved_palette,
            edited_mask,
        )
    else:
        snapped = (sheet_rgb >> 3) << 3
        distinct = np.unique(snapped.reshape(-1, 3), axis=0)
        indices, palette = quantize_median_cut(
            snapped,
            min(16, len(distinct)),
            locked=(snap_gba_5bit(bg_rgb),),
        )
        indices, palette = _background_first(indices, palette, snap_gba_5bit(bg_rgb))
    package_dir.mkdir(parents=True, exist_ok=True)
    save_indexed_png(safe_join(package_dir, "hero.png"), indices, palette)
    write_jasc(
        safe_join(package_dir, "hero.pal"),
        [(int(row[0]), int(row[1]), int(row[2])) for row in palette],
    )
    return package_dir


def _preserve_approved_palette(
    sheet_rgb: np.ndarray,
    approved_indices: np.ndarray,
    approved_palette: np.ndarray,
    edited_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if sheet_rgb.ndim != 3 or sheet_rgb.shape[2] != 3:
        raise ValueError(f"sheet_rgb must be (H, W, 3), got {sheet_rgb.shape}")
    if approved_indices.shape != sheet_rgb.shape[:2]:
        raise ValueError("approved indices must match sheet dimensions")
    if edited_mask.shape != approved_indices.shape or edited_mask.dtype != np.dtype(bool):
        raise ValueError("edited mask must be a bool array matching approved indices")
    if (
        approved_palette.ndim != 2
        or approved_palette.shape[1] != 3
        or not 1 <= len(approved_palette) <= 16
    ):
        raise ValueError("approved palette must be a (1..16, 3) array")
    if approved_indices.size and int(approved_indices.max()) >= len(approved_palette):
        raise ValueError("approved indices contain an out-of-range palette entry")

    indices = approved_indices.copy()
    if bool(np.any(edited_mask)):
        edited_rgb = sheet_rgb[edited_mask].reshape(1, -1, 3)
        indices[edited_mask] = map_to_palette(edited_rgb, approved_palette).reshape(-1)
    return indices, approved_palette.copy()


def candidate_artifacts(workspace: Path, package_dir: Path) -> tuple[Artifact, ...]:
    del workspace
    return tuple(
        Artifact(
            role=role,
            path=f"candidate/package/{path.relative_to(package_dir).as_posix()}",
            sha256=sha256_file(path),
            media_type=media_type,
        )
        for role, path, media_type in (
            ("sheet", safe_join(package_dir, "hero.png"), "image/png"),
            ("palette", safe_join(package_dir, "hero.pal"), "text/plain"),
        )
    )


def candidate_lineage(
    *,
    job_id: str,
    manifest: Manifest,
    prepared: PreparedPortrait,
    reference_pack: ReferencePack | None,
    artifacts: tuple[Artifact, ...],
) -> LineageNode:
    return LineageNode(
        asset_id=f"{job_id}-candidate",
        operation=prepared.operation,
        parents=prepared.parents,
        provider=manifest.provider,
        model=prepared.provider_model,
        prompt=prepared.prompt,
        reference_pack=reference_pack.id if reference_pack else None,
        reference_pack_rev=reference_pack.revision if reference_pack else None,
        seed=prepared.seed,
        params=manifest.params,
        mask=prepared.mask,
        protected_regions=prepared.protected_regions,
        metrics=prepared.metrics,
        output_hashes=tuple(sorted(artifact.sha256 for artifact in artifacts)),
        created_at=utc_now_iso(),
    )


def publish_candidate_atomically(
    workspace: Path,
    snapshot: CandidateSnapshot,
    lineage: LineageNode,
    staged_root: Path,
) -> None:
    candidate_root = safe_join(workspace, "candidate")
    if candidate_root.exists():
        raise FileExistsError(f"candidate already exists for job {snapshot.job_id}")
    data_root = workspace.parents[1]
    moved = False
    lineage_created = False
    try:
        os.replace(staged_root, candidate_root)
        moved = True
        _fsync_directory(workspace)
        CandidateStore(data_root).create_while_job_locked(snapshot)
        LineageStore(data_root).add(lineage)
        lineage_created = True
    except Exception as exc:
        try:
            rollback_candidate_publication(
                workspace,
                lineage.asset_id,
                staged_root,
                candidate_published=moved,
                lineage_published=lineage_created,
            )
        except Exception as cleanup_exc:
            raise cleanup_exc from exc
        raise


def rollback_candidate_publication(
    workspace: Path,
    lineage_id: str,
    staged_root: Path,
    *,
    candidate_published: bool,
    lineage_published: bool,
) -> None:
    if candidate_published:
        _remove_tree(safe_join(workspace, "candidate"))
    if lineage_published:
        LineageStore(workspace.parents[1]).discard_pending(lineage_id)
    _remove_tree(staged_root)


def _remove_tree(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return


def _slot_slice(name: str) -> tuple[slice, slice]:
    slot = _BY_NAME[name]
    return slice(slot.y, slot.y + slot.h), slice(slot.x, slot.x + slot.w)


def _crop(rgb: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    return rgb[y : y + h, x : x + w]


def _render_slot(source: np.ndarray, name: str) -> np.ndarray:
    slot = _BY_NAME[name]
    return resize(source, (slot.w, slot.h), ResizeMode.ILLUSTRATION_FIT)


def _background_first(
    indices: np.ndarray, palette: np.ndarray, bg_rgb: tuple[int, int, int]
) -> tuple[np.ndarray, np.ndarray]:
    bg = np.array(bg_rgb, dtype=np.uint8)
    matches = np.nonzero(np.all(palette == bg, axis=1))[0]
    if matches.size == 0 or matches[0] == 0:
        return indices, palette
    bg_index = int(matches[0])
    swapped_indices = indices.copy()
    swapped_indices[indices == 0] = bg_index
    swapped_indices[indices == bg_index] = 0
    swapped_palette = palette.copy()
    swapped_palette[[0, bg_index]] = swapped_palette[[bg_index, 0]]
    return swapped_indices, swapped_palette
