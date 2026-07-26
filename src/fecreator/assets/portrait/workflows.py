from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np

from fecreator.assets.portrait.alignment import align_to_main
from fecreator.assets.portrait.manifest import GREEN_BG
from fecreator.assets.portrait.prompt_plan import build_prompt_plan
from fecreator.assets.portrait.references import concept_art_artifacts
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import Diagnostic, error, has_errors
from fecreator.contracts.lineage import Operation, Region
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.imaging.io import ImageBudgetError, load_rgb
from fecreator.providers.base import GenRequest, GenResponse, Provider, require_capabilities
from fecreator.references.model import ReferencePack


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
