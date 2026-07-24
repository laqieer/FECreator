from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import cast

import numpy as np

from fecreator.assets.base import SourcePlan
from fecreator.assets.portrait import prompt_plan
from fecreator.assets.portrait.alignment import align_to_main
from fecreator.assets.portrait.manifest import (
    GREEN_BG,
    preferred_capabilities,
    required_capabilities,
)
from fecreator.assets.portrait.references import concept_art_artifacts
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import error, has_errors
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import Artifact, JobResult, StageResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.imaging.io import load_rgb, save_indexed_png
from fecreator.imaging.quantize import quantize_median_cut
from fecreator.imaging.resize import ResizeMode, resize
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.providers.base import GenRequest, Provider, require_capabilities
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore
from fecreator.reporting.bundle import build_bundle
from fecreator.reporting.json_report import build_report, write_report
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
_UPPER_CONTENT = SAFE_ZONES[0]
_LOWER_CONTENT = SAFE_ZONES[1]
_EYE_SLOTS = ("half_closed_eyes", "closed_eyes")
_MOUTH_SLOTS = ("mouth1", "mouth2", "mouth3", "mouth4_status", "mouth5", "mouth6", "mouth7")


def _normalized_path_parts(path: str) -> tuple[str, ...]:
    return tuple(PurePosixPath(path.replace("\\", "/")).parts)


def _safe_artifact_path(workspace: Path, raw_path: str) -> Path:
    return safe_join(workspace, *_normalized_path_parts(raw_path))


def _slot_slice(name: str) -> tuple[slice, slice]:
    slot = _BY_NAME[name]
    return slice(slot.y, slot.y + slot.h), slice(slot.x, slot.x + slot.w)


def _slot_target(name: str) -> tuple[int, int]:
    slot = _BY_NAME[name]
    return slot.w, slot.h


def _crop(rgb: np.ndarray, *, x: int, y: int, w: int, h: int) -> np.ndarray:
    return rgb[y : y + h, x : x + w]


def _render_slot(source: np.ndarray, name: str) -> np.ndarray:
    return resize(source, _slot_target(name), ResizeMode.ILLUSTRATION_FIT)


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


class PortraitPlugin:
    id = "portrait"

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return required_capabilities(workflow)

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return preferred_capabilities(workflow)

    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
        return prompt_plan.plan_sources(manifest, pack)

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        if manifest.workflow != "text_to_portrait":
            raise NotImplementedError(f"workflow not implemented yet: {manifest.workflow}")

        ctx.workspace.mkdir(parents=True, exist_ok=True)
        data_root = ctx.workspace.parents[1]
        pack = self._reference_pack(data_root, manifest)
        provider = cast(Provider, PROVIDER_REGISTRY.get(manifest.provider))
        require_capabilities(provider, self.required_capabilities(manifest.workflow))

        plan = prompt_plan.build_prompt_plan(manifest, pack)
        response = provider.generate(
            GenRequest(
                workflow=manifest.workflow,
                prompt=plan.neutral_prompt,
                references=concept_art_artifacts(pack) if pack else (),
                params=manifest.params,
            ),
            ctx.workspace,
        )
        if not response.ok or not response.artifacts:
            diagnostics = response.diagnostics or (
                error("PROVIDER_NO_ARTIFACTS", "provider returned no artifacts"),
            )
            return JobResult(job_id=ctx.job_id, ok=False, diagnostics=diagnostics)

        neutral = load_rgb(_safe_artifact_path(ctx.workspace, response.artifacts[0].path))
        main = align_to_main(neutral, GREEN_BG)
        package_dir = safe_join(ctx.workspace, "package")
        self._export_package(package_dir, main, GREEN_BG)

        diagnostics = tuple(FeGbaPortraitStandard().validate(package_dir))
        if has_errors(diagnostics):
            return JobResult(job_id=ctx.job_id, ok=False, diagnostics=diagnostics)

        artifacts = self._package_artifacts(ctx.workspace, package_dir)
        output_hashes = tuple(sorted(artifact.sha256 for artifact in artifacts))
        lineage = LineageNode(
            asset_id=ctx.job_id,
            operation=Operation.EXPORT_SPEC,
            provider=manifest.provider,
            model=response.model,
            prompt=plan.neutral_prompt,
            reference_pack=pack.id if pack else None,
            reference_pack_rev=pack.revision if pack else None,
            seed=response.seed,
            params=manifest.params,
            output_hashes=output_hashes,
            created_at=utc_now_iso(),
        )
        LineageStore(data_root).add(lineage)

        job = JobStore(data_root).load(ctx.job_id)
        write_report(
            safe_join(ctx.workspace, "report.json"),
            build_report(
                job,
                [StageResult(stage="export", ok=True, artifacts=artifacts)],
                [lineage],
            ),
        )
        write_json_atomic(
            safe_join(ctx.workspace, "lineage.json"),
            [lineage.model_dump(mode="json")],
        )
        build_bundle(job, ctx.workspace, safe_join(ctx.workspace, "bundle"))
        return JobResult(
            job_id=ctx.job_id,
            ok=True,
            artifacts=artifacts,
            diagnostics=diagnostics,
            lineage_id=lineage.asset_id,
        )

    def _reference_pack(self, data_root: Path, manifest: Manifest) -> ReferencePack | None:
        if manifest.character_ref_pack is None:
            return None
        return ReferencePackStore(data_root).latest(manifest.character_ref_pack)

    def _package_artifacts(self, workspace: Path, package_dir: Path) -> tuple[Artifact, ...]:
        sheet = safe_join(package_dir, "hero.png")
        palette = safe_join(package_dir, "hero.pal")
        return (
            Artifact(
                role="sheet",
                path=sheet.relative_to(workspace).as_posix(),
                sha256=sha256_file(sheet),
                media_type="image/png",
            ),
            Artifact(
                role="palette",
                path=palette.relative_to(workspace).as_posix(),
                sha256=sha256_file(palette),
                media_type="text/plain",
            ),
        )

    def _export_package(
        self, package_dir: Path, main_rgb: np.ndarray, bg_rgb: tuple[int, int, int]
    ) -> Path:
        if tuple(main_rgb.shape) != (_MAIN_SLOT.h, _MAIN_SLOT.w, 3):
            raise ValueError(
                f"main_rgb must be {_MAIN_SLOT.h}x{_MAIN_SLOT.w} RGB, got {main_rgb.shape}"
            )

        canvas = np.full((SHEET_H, SHEET_W, 3), bg_rgb, dtype=np.uint8)
        canvas[_slot_slice("main")] = main_rgb

        upper = _crop(
            main_rgb,
            x=_UPPER_CONTENT.x,
            y=_UPPER_CONTENT.y,
            w=_UPPER_CONTENT.w,
            h=_UPPER_CONTENT.h,
        )
        lower = _crop(
            main_rgb,
            x=_LOWER_CONTENT.x,
            y=_LOWER_CONTENT.y,
            w=_LOWER_CONTENT.w,
            h=_LOWER_CONTENT.h,
        )
        canvas[_slot_slice("mini")] = _render_slot(main_rgb, "mini")
        for name in _EYE_SLOTS:
            canvas[_slot_slice(name)] = _render_slot(upper, name)
        for name in _MOUTH_SLOTS:
            canvas[_slot_slice(name)] = _render_slot(lower, name)
        for zone in BACKGROUND_ZONES:
            canvas[zone.y : zone.y + zone.h, zone.x : zone.x + zone.w] = bg_rgb

        snapped = (canvas >> 3) << 3
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
