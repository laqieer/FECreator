from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np

from fecreator.assets.portrait.alignment import align_to_main
from fecreator.assets.portrait.expressions import assemble_refined_expressions
from fecreator.assets.portrait.manifest import GREEN_BG
from fecreator.assets.portrait.prompt_plan import build_prompt_plan
from fecreator.assets.portrait.references import concept_art_artifacts
from fecreator.assets.portrait.variants import build_variant
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import Diagnostic, error, has_errors
from fecreator.contracts.lineage import Operation, Region
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.imaging.io import (
    ImageBudgetError,
    has_trns,
    is_indexed_png,
    load_indexed,
    load_rgb,
    png_bit_depth,
    png_dimensions,
)
from fecreator.providers.base import GenRequest, GenResponse, Provider, require_capabilities
from fecreator.references.model import ReferencePack
from fecreator.specs.fire_emblem.gba.portrait_standard.assembly import (
    extract_rgb_slot,
    replace_rgb_slot,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import MAX_COLORS, SHEET_H, SHEET_W
from fecreator.specs.fire_emblem.gba.portrait_standard.palette import read_jasc, snap_gba_5bit

_EXPRESSION_ROLES = ("half_closed_eyes", "closed_eyes", "mouth1", "mouth2", "mouth3")


class WorkflowFailure(Exception):
    """A workflow could not prepare a valid provider result."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__(
            ", ".join(f"{diagnostic.code}: {diagnostic.message}" for diagnostic in diagnostics)
        )
        self.diagnostics = diagnostics


class WorkflowInputError(WorkflowFailure):
    """A workflow-specific immutable input is absent or unsafe."""


@dataclass(frozen=True)
class PreparedPortrait:
    sheet_rgb: np.ndarray
    operation: Operation
    provider_model: str | None
    prompt: str | None
    seed: int | None
    diagnostics: tuple[Diagnostic, ...]
    parents: tuple[str, ...] = ()
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class _ApprovedSheet:
    rgb: np.ndarray
    artifact: Artifact


def prepare_text_to_portrait(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    require_capabilities(provider, {Capability.TEXT_TO_IMAGE})
    return _prepare(
        manifest,
        pack,
        provider,
        workspace,
        operation=Operation.CREATE_NEUTRAL,
        references=concept_art_artifacts(pack) if pack else (),
    )


def prepare_concept_to_portrait(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    references = _concept_inputs(manifest, pack, workspace)
    if not references:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept_to_portrait requires concept art"),)
        )
    return _prepare(
        manifest,
        pack,
        provider,
        workspace,
        operation=Operation.IMPORT_CONCEPT,
        references=references,
    )


def prepare_expression_refine(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    approved = _load_approved_sheet(workspace, manifest)
    require_capabilities(provider, {Capability.IMAGE_TO_IMAGE})
    plan = build_prompt_plan(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=_expression_prompt(plan.expression_prompts),
            references=(approved.artifact, *(concept_art_artifacts(pack) if pack else ())),
            params=manifest.params,
        ),
        workspace,
    )
    cells = _load_expression_cells(response, workspace)
    try:
        refined = assemble_refined_expressions(approved.rgb, cells)
    except ValueError as exc:
        raise WorkflowFailure(
            tuple(response.diagnostics)
            + (error("PROVIDER_INVALID_RESPONSE", "provider returned invalid expression cells"),)
        ) from exc
    return PreparedPortrait(
        sheet_rgb=refined,
        operation=Operation.REFINE_EXPRESSION,
        provider_model=response.model,
        prompt=_expression_prompt(plan.expression_prompts),
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
    )


def prepare_masked_variant(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    approved = _load_approved_sheet(workspace, manifest)
    if manifest.edit is None:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "masked_variant requires an edit mask"),)
        )
    mask, mask_artifact = _load_bool_mask(workspace, manifest.edit.mask_path)
    base_main = extract_rgb_slot(approved.rgb, "main")
    if mask.shape != base_main.shape[:2]:
        raise WorkflowInputError(
            (
                error(
                    "WORKFLOW_INPUT_MISSING",
                    f"mask shape {mask.shape} must match main portrait {base_main.shape[:2]}",
                ),
            )
        )
    require_capabilities(provider, {Capability.MASKED_EDIT})
    plan = build_prompt_plan(manifest, pack)
    prompt = f"{plan.neutral_prompt}, masked variant; change only the supplied mask"
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=prompt,
            references=(approved.artifact, *(concept_art_artifacts(pack) if pack else ())),
            mask=mask_artifact,
            protected_regions=manifest.edit.protected_regions,
            params=manifest.params,
        ),
        workspace,
    )
    edited = _load_single_variant(response, workspace)
    try:
        result, diagnostics = build_variant(
            base_main,
            edited,
            mask,
            manifest.edit.protected_regions,
        )
    except ValueError as exc:
        raise WorkflowFailure(
            tuple(response.diagnostics)
            + (error("PROVIDER_INVALID_RESPONSE", "provider returned an invalid variant image"),)
        ) from exc
    if has_errors(diagnostics):
        raise WorkflowFailure(tuple(response.diagnostics) + tuple(diagnostics))
    return PreparedPortrait(
        sheet_rgb=replace_rgb_slot(approved.rgb, "main", result),
        operation=Operation.VARIANT_MASKED_EDIT,
        provider_model=response.model,
        prompt=prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics) + tuple(diagnostics),
        mask=manifest.edit.mask_path,
        protected_regions=manifest.edit.protected_regions,
    )


def _prepare(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
    *,
    operation: Operation,
    references: tuple[Artifact, ...],
) -> PreparedPortrait:
    from fecreator.assets.portrait.manifest import required_capabilities

    require_capabilities(provider, required_capabilities(manifest.workflow))
    plan = build_prompt_plan(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=plan.neutral_prompt,
            references=references,
            params=manifest.params,
        ),
        workspace,
    )
    artifact = _require_neutral_artifact(response)
    try:
        neutral = load_rgb(_safe_provider_artifact(workspace, artifact.path))
    except (ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise WorkflowFailure(
            response.diagnostics
            + (
                error(
                    "PROVIDER_INVALID_RESPONSE",
                    "provider returned an invalid neutral artifact path or image payload",
                ),
            )
        ) from exc
    return PreparedPortrait(
        sheet_rgb=_assemble_candidate_sheet(align_to_main(neutral, GREEN_BG), GREEN_BG),
        operation=operation,
        provider_model=response.model,
        prompt=plan.neutral_prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
    )


def _load_approved_sheet(workspace: Path, manifest: Manifest) -> _ApprovedSheet:
    sources = tuple(source for source in manifest.sources if source.kind == "approved_portrait")
    if len(sources) != 1:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "workflow requires exactly one approved portrait"),)
        )
    source = sources[0]
    try:
        filename = _submitted_filename(source.ref)
        path = safe_join(workspace, "submitted", filename)
        palette_path = safe_join(workspace, "submitted", f"{Path(filename).stem}.pal")
        if not path.is_file() or not palette_path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.casefold() != ".png":
            raise ValueError("approved portrait must be a PNG")
        if not is_indexed_png(path) or png_bit_depth(path) != 8 or has_trns(path):
            raise ValueError("approved portrait must be an opaque 8-bit indexed PNG")
        width, height = png_dimensions(path)
        if (width, height) != (SHEET_W, SHEET_H):
            raise ValueError(f"approved portrait must be {SHEET_W}x{SHEET_H}")
        indices, palette = load_indexed(path)
        jasc = read_jasc(palette_path)
        if not 1 <= len(palette) <= MAX_COLORS:
            raise ValueError("approved portrait palette must contain 1..16 colours")
        if indices.size and int(indices.max()) >= len(palette):
            raise ValueError("approved portrait uses an out-of-range palette index")
        palette_rows = [(int(row[0]), int(row[1]), int(row[2])) for row in palette]
        if jasc != palette_rows:
            raise ValueError("approved portrait JASC palette does not match its PNG palette")
        if palette_rows[0] != GREEN_BG or any(row != snap_gba_5bit(row) for row in palette_rows):
            raise ValueError("approved portrait palette is not canonical")
    except (FileNotFoundError, ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise WorkflowInputError(
            (
                error(
                    "WORKFLOW_INPUT_MISSING",
                    "approved portrait must be a valid submitted indexed PNG "
                    "with matching JASC palette",
                ),
            )
        ) from exc
    return _ApprovedSheet(
        rgb=palette[indices],
        artifact=Artifact(
            role="approved_portrait",
            path=f"submitted/{filename}",
            sha256=sha256_file(path),
            media_type="image/png",
        ),
    )


def _load_bool_mask(workspace: Path, raw_path: str) -> tuple[np.ndarray, Artifact]:
    try:
        filename = _submitted_filename(raw_path)
        path = safe_join(workspace, "submitted", filename)
        if not path.is_file() or path.suffix.casefold() != ".png":
            raise FileNotFoundError(path)
        png_dimensions(path)
        rgb = load_rgb(path)
        monochrome = np.all(rgb == rgb[:, :, :1], axis=2)
        binary = np.logical_or(rgb[:, :, 0] == 0, rgb[:, :, 0] == 255)
        if not bool(np.all(monochrome & binary)):
            raise ValueError("mask must contain only black and white pixels")
    except (FileNotFoundError, ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "mask must be a valid submitted black-and-white PNG"),)
        ) from exc
    return (
        rgb[:, :, 0] == 255,
        Artifact(
            role="mask",
            path=f"submitted/{filename}",
            sha256=sha256_file(path),
            media_type="image/png",
        ),
    )


def _submitted_filename(raw_path: str) -> str:
    normalized = PurePosixPath(raw_path.replace("\\", "/"))
    if len(normalized.parts) != 1 or normalized.name in {"", ".", ".."}:
        raise ValueError("submitted source must be a filename")
    return normalized.name


def _expression_prompt(expression_prompts: Mapping[str, str]) -> str:
    return "; ".join(f"{role}: {expression_prompts[role]}" for role in _EXPRESSION_ROLES)


def _load_expression_cells(response: GenResponse, workspace: Path) -> dict[str, np.ndarray]:
    _require_success_response(response)
    by_role: dict[str, Artifact] = {}
    for artifact in response.artifacts:
        if artifact.role in by_role:
            raise _invalid_provider_response(
                response, "provider returned duplicate expression roles"
            )
        by_role[artifact.role] = artifact
    roles = frozenset(by_role)
    expected = frozenset(_EXPRESSION_ROLES)
    if roles != expected:
        raise _invalid_provider_response(
            response, "provider did not return the complete expression roles"
        )
    cells: dict[str, np.ndarray] = {}
    for role in _EXPRESSION_ROLES:
        artifact = by_role[role]
        if artifact.media_type != "image/png":
            raise _invalid_provider_response(response, "expression artifact must be an image/png")
        image = _load_verified_provider_image(workspace, artifact, response)
        if image.shape != (16, 32, 3):
            raise _invalid_provider_response(
                response, "expression artifact has an invalid cell shape"
            )
        cells[role] = image
    return cells


def _load_single_variant(response: GenResponse, workspace: Path) -> np.ndarray:
    _require_success_response(response)
    if len(response.artifacts) != 1 or response.artifacts[0].media_type != "image/png":
        raise _invalid_provider_response(
            response,
            "provider must return exactly one image/png variant artifact",
        )
    return _load_verified_provider_image(workspace, response.artifacts[0], response)


def _require_success_response(response: GenResponse) -> None:
    if response.ok and not has_errors(response.diagnostics):
        return
    diagnostics = tuple(response.diagnostics)
    if not response.ok and not has_errors(diagnostics):
        diagnostics += (error("PROVIDER_FAILED", "provider reported failure"),)
    raise WorkflowFailure(diagnostics)


def _load_verified_provider_image(
    workspace: Path,
    artifact: Artifact,
    response: GenResponse,
) -> np.ndarray:
    try:
        path = _safe_provider_artifact(workspace, artifact.path)
        if not path.is_file() or sha256_file(path) != artifact.sha256:
            raise ValueError("artifact path is missing or hash does not match")
        return load_rgb(path)
    except (FileNotFoundError, ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise _invalid_provider_response(
            response,
            "provider returned an invalid image artifact path or payload",
        ) from exc


def _invalid_provider_response(response: GenResponse, message: str) -> WorkflowFailure:
    return WorkflowFailure(
        tuple(response.diagnostics) + (error("PROVIDER_INVALID_RESPONSE", message),)
    )


def _require_neutral_artifact(response: GenResponse) -> Artifact:
    if not response.ok:
        diagnostics = tuple(response.diagnostics)
        if not has_errors(diagnostics):
            diagnostics += (error("PROVIDER_FAILED", "provider reported failure"),)
        raise WorkflowFailure(diagnostics)
    if not response.artifacts:
        raise WorkflowFailure(
            tuple(response.diagnostics)
            + (error("PROVIDER_NO_ARTIFACTS", "provider returned no artifacts"),)
        )

    images = tuple(
        artifact for artifact in response.artifacts if artifact.media_type.startswith("image/")
    )
    neutrals = tuple(artifact for artifact in images if artifact.role == "neutral")
    if len(neutrals) == 1:
        return neutrals[0]
    if not neutrals and len(images) == 1:
        return images[0]
    raise WorkflowFailure(
        tuple(response.diagnostics)
        + (
            error(
                "PROVIDER_INVALID_RESPONSE",
                "provider did not return exactly one usable neutral image artifact",
            ),
        )
    )


def _safe_provider_artifact(workspace: Path, raw_path: str) -> Path:
    return safe_join(workspace, *PurePosixPath(raw_path.replace("\\", "/")).parts)


def _concept_inputs(
    manifest: Manifest,
    pack: ReferencePack | None,
    workspace: Path,
) -> tuple[Artifact, ...]:
    submitted = tuple(
        _submitted_concept_artifact(workspace, source.kind, source.ref)
        for source in manifest.sources
        if source.kind == "concept_art"
    )
    return (*submitted, *(concept_art_artifacts(pack) if pack else ()))


def _submitted_concept_artifact(workspace: Path, role: str, ref: str) -> Artifact:
    normalized = PurePosixPath(ref.replace("\\", "/"))
    if len(normalized.parts) != 1 or normalized.name in {"", ".", ".."}:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept source ref must be a submitted filename"),)
        )
    try:
        path = safe_join(workspace, "submitted", normalized.name)
        if not path.is_file():
            raise FileNotFoundError(path)
        load_rgb(path)
    except (FileNotFoundError, ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept source must be a valid submitted image"),)
        ) from exc
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type is None or not media_type.startswith("image/"):
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept source must be an image file"),)
        )
    return Artifact(
        role=role,
        path=f"submitted/{normalized.name}",
        sha256=sha256_file(path),
        media_type=media_type,
    )


def _assemble_candidate_sheet(main_rgb: np.ndarray, bg_rgb: tuple[int, int, int]) -> np.ndarray:
    from fecreator.assets.portrait.candidate import assemble_candidate_sheet

    return assemble_candidate_sheet(main_rgb, bg_rgb)
