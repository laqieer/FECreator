from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast

import numpy as np
from pydantic import ValidationError

from fecreator.assets.dialogue_background.prompt_plan import build_prompt
from fecreator.assets.portrait.references import concept_art_artifacts
from fecreator.assets.portrait.variants import build_variant
from fecreator.assets.reviewed import AssetWorkflowFailure
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import Diagnostic, error, has_errors
from fecreator.contracts.dialogue_background import DialogueBackgroundPackageManifest
from fecreator.contracts.lineage import Operation, Region
from fecreator.contracts.manifest import AssetMetadata, Manifest
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.imaging.io import ImageBudgetError, load_opaque_png_rgb
from fecreator.providers.base import GenRequest, GenResponse, Provider, require_capabilities
from fecreator.references.model import ReferencePack

_WIDTH = 240
_HEIGHT = 160
_PREFERRED_ROLES = ("background", "variant", "neutral")


class WorkflowFailure(AssetWorkflowFailure):
    """A dialogue-background workflow could not prepare a valid provider result."""


class WorkflowInputError(WorkflowFailure):
    """A dialogue-background workflow input is absent or unsafe."""


@dataclass(frozen=True)
class PreparedDialogueBackground:
    rgb: np.ndarray
    operation: Operation
    provider_model: str | None
    prompt: str | None
    seed: int | None
    diagnostics: tuple[Diagnostic, ...]
    inputs: tuple[Artifact, ...]
    parents: tuple[str, ...] = ()
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=lambda: {"width": 240.0, "height": 160.0})


@dataclass(frozen=True)
class _ApprovedBackground:
    rgb: np.ndarray
    png_artifact: Artifact
    manifest_artifact: Artifact


def prepare_text_to_dialogue_background(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedDialogueBackground:
    require_capabilities(provider, {Capability.TEXT_TO_IMAGE})
    references = concept_art_artifacts(pack) if pack else ()
    return _generate(
        manifest,
        pack,
        provider,
        workspace,
        operation=Operation.CREATE_DIALOGUE_BACKGROUND,
        references=references,
    )


def prepare_concept_to_dialogue_background(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedDialogueBackground:
    references = _concept_inputs(manifest, pack, workspace)
    if not references:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept workflow requires concept art"),)
        )
    require_capabilities(provider, {Capability.IMAGE_TO_IMAGE})
    return _generate(
        manifest,
        pack,
        provider,
        workspace,
        operation=Operation.IMPORT_DIALOGUE_BACKGROUND_CONCEPT,
        references=references,
    )


def prepare_masked_variant(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedDialogueBackground:
    if manifest.edit is None:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "masked_variant requires an edit mask"),)
        )
    approved = _load_approved_background(workspace, manifest)
    edit = manifest.edit
    mask, mask_artifact = _load_bool_mask(workspace, edit.mask_path)
    if mask.shape != approved.rgb.shape[:2]:
        raise WorkflowInputError(
            (
                error(
                    "WORKFLOW_INPUT_MISSING",
                    f"mask shape {mask.shape} must match background {approved.rgb.shape[:2]}",
                ),
            )
        )
    require_capabilities(provider, {Capability.MASKED_EDIT})
    prompt = build_prompt(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=prompt,
            references=(approved.png_artifact,),
            mask=mask_artifact,
            protected_regions=edit.protected_regions,
            params=manifest.params,
        ),
        workspace,
    )
    edited = _load_selected_background(
        response, workspace, cast(AssetMetadata, manifest.metadata).name
    )
    try:
        result, diagnostics = build_variant(approved.rgb, edited, mask, edit.protected_regions)
    except ValueError as exc:
        raise WorkflowFailure(
            tuple(response.diagnostics)
            + (error("PROVIDER_INVALID_RESPONSE", "provider returned an invalid background"),)
        ) from exc
    if has_errors(diagnostics):
        raise WorkflowFailure(tuple(response.diagnostics) + tuple(diagnostics))
    if manifest.parent_asset_id is None:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "masked_variant requires parent_asset_id"),)
        )
    return PreparedDialogueBackground(
        rgb=result,
        operation=Operation.VARIANT_MASKED_EDIT,
        provider_model=response.model,
        prompt=prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics) + tuple(diagnostics),
        inputs=(approved.png_artifact, approved.manifest_artifact, mask_artifact),
        parents=(manifest.parent_asset_id,),
        mask=edit.mask_path,
        protected_regions=edit.protected_regions,
    )


def _generate(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
    *,
    operation: Operation,
    references: tuple[Artifact, ...],
) -> PreparedDialogueBackground:
    prompt = build_prompt(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=prompt,
            references=references,
            params=manifest.params,
        ),
        workspace,
    )
    metadata = cast(AssetMetadata, manifest.metadata)
    rgb = _load_selected_background(response, workspace, metadata.name)
    return PreparedDialogueBackground(
        rgb=rgb,
        operation=operation,
        provider_model=response.model,
        prompt=prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
        inputs=references,
    )


def _load_selected_background(response: GenResponse, workspace: Path, name: str) -> np.ndarray:
    _require_success_response(response)
    images = tuple(
        artifact for artifact in response.artifacts if artifact.media_type == "image/png"
    )
    preferred_roles = (name, *_PREFERRED_ROLES)
    for role in preferred_roles:
        selected = tuple(artifact for artifact in images if artifact.role == role)
        if len(selected) == 1:
            return _load_verified_provider_png(workspace, selected[0], response)
        if len(selected) > 1:
            raise _invalid_provider_response(
                response, f"provider returned duplicate {role} artifacts"
            )
    if len(images) == 1:
        return _load_verified_provider_png(workspace, images[0], response)
    raise _invalid_provider_response(
        response,
        "provider did not return exactly one usable dialogue background image artifact",
    )


def _load_verified_provider_png(
    workspace: Path, artifact: Artifact, response: GenResponse
) -> np.ndarray:
    try:
        path = _workspace_artifact(workspace, artifact.path)
        if not path.is_file() or path.is_symlink() or sha256_file(path) != artifact.sha256:
            raise ValueError("artifact path is missing, unsafe, or hash does not match")
        rgb, _mode = load_opaque_png_rgb(path)
        _validate_background_dimensions(rgb)
        return rgb
    except (FileNotFoundError, ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise _invalid_provider_response(
            response,
            "provider returned an invalid dialogue background artifact path or payload",
        ) from exc


def _load_approved_background(workspace: Path, manifest: Manifest) -> _ApprovedBackground:
    sources = tuple(
        source for source in manifest.sources if source.kind == "approved_dialogue_background"
    )
    if len(sources) != 1:
        raise WorkflowInputError(
            (
                error(
                    "WORKFLOW_INPUT_MISSING",
                    "workflow requires exactly one approved dialogue background",
                ),
            )
        )
    try:
        filename = _submitted_filename(sources[0].ref)
        png_path = safe_join(workspace, "submitted", filename)
        manifest_path = safe_join(workspace, "submitted", f"{Path(filename).stem}.manifest.json")
        if (
            png_path.suffix.casefold() != ".png"
            or not png_path.is_file()
            or png_path.is_symlink()
            or not manifest_path.is_file()
            or manifest_path.is_symlink()
        ):
            raise FileNotFoundError(png_path)
        rgb, _mode = load_opaque_png_rgb(png_path)
        _validate_background_dimensions(rgb)
        package_manifest = DialogueBackgroundPackageManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if package_manifest.name != Path(
            filename
        ).stem or package_manifest.png_sha256 != sha256_file(png_path):
            raise ValueError("approved package manifest does not match background")
    except (
        FileNotFoundError,
        ImageBudgetError,
        OSError,
        PathEscapeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise WorkflowInputError(
            (
                error(
                    "WORKFLOW_INPUT_MISSING",
                    "approved dialogue background must be a valid submitted package",
                ),
            )
        ) from exc
    return _ApprovedBackground(
        rgb=rgb,
        png_artifact=Artifact(
            role="approved_dialogue_background",
            path=f"submitted/{filename}",
            sha256=sha256_file(png_path),
            media_type="image/png",
        ),
        manifest_artifact=Artifact(
            role="approved_dialogue_background_manifest",
            path=f"submitted/{manifest_path.name}",
            sha256=sha256_file(manifest_path),
            media_type="application/json",
        ),
    )


def _load_bool_mask(workspace: Path, raw_path: str) -> tuple[np.ndarray, Artifact]:
    try:
        filename = _submitted_filename(raw_path)
        path = safe_join(workspace, "submitted", filename)
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".png":
            raise FileNotFoundError(path)
        rgb, _mode = load_opaque_png_rgb(path)
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


def _concept_inputs(
    manifest: Manifest, pack: ReferencePack | None, workspace: Path
) -> tuple[Artifact, ...]:
    submitted = tuple(
        _submitted_concept_artifact(workspace, source.ref)
        for source in manifest.sources
        if source.kind == "concept_art"
    )
    return (*submitted, *(concept_art_artifacts(pack) if pack else ()))


def _submitted_concept_artifact(workspace: Path, ref: str) -> Artifact:
    try:
        filename = _submitted_filename(ref)
        path = safe_join(workspace, "submitted", filename)
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".png":
            raise FileNotFoundError(path)
        media_type, _encoding = mimetypes.guess_type(path.name)
        if media_type != "image/png":
            raise ValueError("concept source must be a PNG image")
        load_opaque_png_rgb(path)
    except (FileNotFoundError, ImageBudgetError, OSError, PathEscapeError, ValueError) as exc:
        raise WorkflowInputError(
            (error("WORKFLOW_INPUT_MISSING", "concept source must be a valid submitted image"),)
        ) from exc
    return Artifact(
        role="concept_art",
        path=f"submitted/{filename}",
        sha256=sha256_file(path),
        media_type=media_type,
    )


def _require_success_response(response: GenResponse) -> None:
    if response.ok and not has_errors(response.diagnostics):
        return
    diagnostics = tuple(response.diagnostics)
    if not response.ok and not has_errors(diagnostics):
        diagnostics += (error("PROVIDER_FAILED", "provider reported failure"),)
    raise WorkflowFailure(diagnostics)


def _invalid_provider_response(response: GenResponse, message: str) -> WorkflowFailure:
    return WorkflowFailure(
        tuple(response.diagnostics) + (error("PROVIDER_INVALID_RESPONSE", message),)
    )


def _validate_background_dimensions(rgb: np.ndarray) -> None:
    if rgb.shape != (_HEIGHT, _WIDTH, 3):
        raise ValueError(f"background must be {_WIDTH}x{_HEIGHT}")


def _submitted_filename(raw_path: str) -> str:
    normalized = PurePosixPath(raw_path.replace("\\", "/"))
    if len(normalized.parts) != 1 or normalized.name in {"", ".", ".."}:
        raise ValueError("submitted source must be a filename")
    return normalized.name


def _workspace_artifact(workspace: Path, raw_path: str) -> Path:
    normalized = PurePosixPath(raw_path.replace("\\", "/"))
    if (
        normalized.is_absolute()
        or not normalized.parts
        or any(part in {"", ".", ".."} for part in normalized.parts)
    ):
        raise PathEscapeError("provider artifact path is unsafe")
    return safe_join(workspace, *normalized.parts)
