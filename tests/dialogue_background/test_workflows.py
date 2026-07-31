from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fecreator.assets.dialogue_background.plugin import DialogueBackgroundPlugin
from fecreator.assets.dialogue_background.workflows import (
    WorkflowFailure,
    WorkflowInputError,
    prepare_concept_to_dialogue_background,
    prepare_masked_variant,
    prepare_text_to_dialogue_background,
)
from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)
from fecreator.contracts.lineage import Region
from fecreator.contracts.manifest import (
    AssetMetadata,
    EditSpec,
    Manifest,
    SourceIdentity,
    SourceSpec,
)
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import save_canonical_rgb_png, save_png
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal


def _metadata() -> AssetMetadata:
    return AssetMetadata(
        name="phantom_city",
        purpose="Original phantom city",
        source=SourceIdentity(kind="prompt", id="bg/phantom-city", revision="1"),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
    )


def _manifest(
    workflow: str = "text_to_dialogue_background",
    *,
    sources: tuple[SourceSpec, ...] = (SourceSpec(kind="text", ref="phantom city"),),
    parent_asset_id: str | None = None,
    edit: EditSpec | None = None,
) -> Manifest:
    return Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow=workflow,
        provider="test-provider",
        metadata=_metadata(),
        parent_asset_id=parent_asset_id,
        sources=sources,
        edit=edit,
        params={"width": 240, "height": 160},
    )


def _background() -> np.ndarray:
    return np.full((160, 240, 3), (20, 40, 60), dtype=np.uint8)


class _Provider:
    id = "test-provider"
    capabilities = CapabilitySet(capabilities=frozenset(Capability))

    def __init__(self, image: np.ndarray | None = None) -> None:
        self.image = _background() if image is None else image
        self.requests: list[GenRequest] = []

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        self.requests.append(request)
        output = workspace / "generated" / "background.png"
        save_png(output, self.image)
        return GenResponse(
            ok=True,
            artifacts=(
                Artifact(
                    role="background",
                    path="generated/background.png",
                    sha256=sha256_file(output),
                    media_type="image/png",
                ),
            ),
            model="test-model",
            seed=7,
        )


def test_plugin_declares_required_capabilities() -> None:
    plugin = DialogueBackgroundPlugin()

    assert plugin.required_capabilities("text_to_dialogue_background") == {Capability.TEXT_TO_IMAGE}
    assert plugin.required_capabilities("concept_to_dialogue_background") == {
        Capability.IMAGE_TO_IMAGE
    }
    assert plugin.required_capabilities("masked_variant") == {Capability.MASKED_EDIT}


def test_source_plan_documents_opaque_240x160_contract() -> None:
    plan = DialogueBackgroundPlugin().plan_sources(_manifest(), None)

    assert plan.expected_filenames == ("phantom_city.png",)
    assert "240x160" in plan.background_contract
    assert "opaque" in plan.background_contract
    assert plan.forbidden_colors == ()


def test_concept_workflow_rejects_missing_concept_input(tmp_path: Path) -> None:
    with pytest.raises(WorkflowInputError, match="concept"):
        prepare_concept_to_dialogue_background(
            _manifest("concept_to_dialogue_background"),
            None,
            _Provider(),
            tmp_path / "workspace",
        )


def test_concept_workflow_refuses_missing_provider_capability(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    save_png(workspace / "submitted" / "concept.png", _background())

    class _NoImageProvider(_Provider):
        capabilities = CapabilitySet(capabilities=frozenset())

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            raise AssertionError("must refuse before generating")

    with pytest.raises(ProviderRefusal, match="image_to_image"):
        prepare_concept_to_dialogue_background(
            _manifest(
                "concept_to_dialogue_background",
                sources=(SourceSpec(kind="concept_art", ref="concept.png"),),
            ),
            None,
            _NoImageProvider(),
            workspace,
        )


def test_concept_workflow_rejects_non_regular_submitted_input(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "submitted" / "concept.png").mkdir(parents=True)

    with pytest.raises(WorkflowInputError, match="concept source"):
        prepare_concept_to_dialogue_background(
            _manifest(
                "concept_to_dialogue_background",
                sources=(SourceSpec(kind="concept_art", ref="concept.png"),),
            ),
            None,
            _Provider(),
            workspace,
        )


def test_text_workflow_rejects_provider_artifact_with_declared_hash_mismatch(
    tmp_path: Path,
) -> None:
    class _HashMismatchProvider(_Provider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            output = workspace / "generated" / "background.png"
            save_png(output, _background())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="background",
                        path="generated/background.png",
                        sha256="0" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    with pytest.raises(WorkflowFailure, match="invalid dialogue background artifact"):
        prepare_text_to_dialogue_background(_manifest(), None, _HashMismatchProvider(), tmp_path)


def test_text_workflow_rejects_provider_artifact_outside_workspace(tmp_path: Path) -> None:
    class _OutsideWorkspaceProvider(_Provider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="background",
                        path="../background.png",
                        sha256="0" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    with pytest.raises(WorkflowFailure, match="invalid dialogue background artifact"):
        prepare_text_to_dialogue_background(
            _manifest(), None, _OutsideWorkspaceProvider(), tmp_path
        )


def _seed_approved_background(workspace: Path) -> np.ndarray:
    background = _background()
    path = workspace / "submitted" / "approved.png"
    save_canonical_rgb_png(path, background)
    package_manifest = DialogueBackgroundPackageManifest(
        name="approved",
        purpose="Approved background",
        provider="manual",
        source=DialogueBackgroundSourceRecord(
            kind="prompt",
            id="bg/approved",
            revision="1",
            input_sha256="0" * 64,
        ),
        png_sha256=sha256_file(path),
        license_note="Original repository fixture.",
        source_note="Approved fixture.",
    )
    (workspace / "submitted" / "approved.manifest.json").write_text(
        json.dumps(package_manifest.model_dump(mode="json")),
        encoding="utf-8",
    )
    return background


def test_masked_variant_keeps_pixels_outside_binary_mask(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    approved = _seed_approved_background(workspace)
    mask = np.zeros((160, 240, 3), dtype=np.uint8)
    mask[40:80, 60:100] = 255
    save_png(workspace / "submitted" / "mask.png", mask)
    edited = np.full((160, 240, 3), (200, 80, 20), dtype=np.uint8)

    prepared = prepare_masked_variant(
        _manifest(
            "masked_variant",
            sources=(SourceSpec(kind="approved_dialogue_background", ref="approved.png"),),
            parent_asset_id="approved-background",
            edit=EditSpec(mask_path="mask.png"),
        ),
        None,
        _Provider(edited),
        workspace,
    )

    assert np.array_equal(prepared.rgb[mask[:, :, 0] == 0], approved[mask[:, :, 0] == 0])
    assert np.array_equal(prepared.rgb[mask[:, :, 0] == 255], edited[mask[:, :, 0] == 255])
    assert prepared.parents == ("approved-background",)
    assert [artifact.role for artifact in prepared.inputs] == [
        "approved_dialogue_background",
        "approved_dialogue_background_manifest",
        "mask",
    ]


def test_masked_variant_rejects_changes_to_protected_region(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _seed_approved_background(workspace)
    mask = np.zeros((160, 240, 3), dtype=np.uint8)
    mask[40:80, 60:100] = 255
    save_png(workspace / "submitted" / "mask.png", mask)
    edited = np.full((160, 240, 3), (200, 80, 20), dtype=np.uint8)

    with pytest.raises(WorkflowFailure, match="PROTECTED_REGION_CHANGED"):
        prepare_masked_variant(
            _manifest(
                "masked_variant",
                sources=(SourceSpec(kind="approved_dialogue_background", ref="approved.png"),),
                parent_asset_id="approved-background",
                edit=EditSpec(
                    mask_path="mask.png",
                    protected_regions=(Region(x=60, y=40, w=40, h=40, label="protected"),),
                ),
            ),
            None,
            _Provider(edited),
            workspace,
        )
