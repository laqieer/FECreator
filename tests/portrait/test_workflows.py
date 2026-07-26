from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fecreator.assets.portrait.workflows import (
    WorkflowFailure,
    WorkflowInputError,
    prepare_concept_to_portrait,
    prepare_expression_refine,
    prepare_masked_variant,
    prepare_text_to_portrait,
)
from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.lineage import Operation, Region
from fecreator.contracts.manifest import EditSpec, Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import save_png
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal
from tests.fixtures.gba import write_valid_package


def _manifest(workflow: str, sources: tuple[SourceSpec, ...]) -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow=workflow,
        provider="test-provider",
        sources=sources,
    )


def _portrait_rgb() -> np.ndarray:
    rgb = np.full((80, 96, 3), (0, 248, 0), dtype=np.uint8)
    rgb[20:60, 20:60] = (200, 40, 40)
    return rgb


class _Provider:
    id = "test-provider"
    capabilities = CapabilitySet(capabilities=frozenset(Capability))

    def __init__(self) -> None:
        self.requests: list[GenRequest] = []

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        self.requests.append(request)
        output = workspace / "generated" / "neutral.png"
        save_png(output, _portrait_rgb())
        return GenResponse(
            ok=True,
            artifacts=(
                Artifact(
                    role="neutral",
                    path="generated/neutral.png",
                    sha256=sha256_file(output),
                    media_type="image/png",
                ),
            ),
            model="test-model",
            seed=7,
        )


def test_text_workflow_prepares_candidate_sheet_from_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    provider = _Provider()

    prepared = prepare_text_to_portrait(
        _manifest("text_to_portrait", (SourceSpec(kind="text", ref="red knight"),)),
        None,
        provider,
        workspace,
    )

    assert prepared.operation is Operation.CREATE_NEUTRAL
    assert prepared.sheet_rgb.shape == (112, 128, 3)
    assert provider.requests[0].references == ()


def test_concept_workflow_passes_immutable_submitted_artifact_to_image_provider(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    concept = workspace / "submitted" / "concept.png"
    save_png(concept, _portrait_rgb())
    provider = _Provider()

    prepared = prepare_concept_to_portrait(
        _manifest(
            "concept_to_portrait",
            (SourceSpec(kind="concept_art", ref="concept.png"),),
        ),
        None,
        provider,
        workspace,
    )

    assert prepared.operation is Operation.IMPORT_CONCEPT
    assert provider.requests[0].references == (
        Artifact(
            role="concept_art",
            path="submitted/concept.png",
            sha256=sha256_file(concept),
            media_type="image/png",
        ),
    )


def test_concept_workflow_rejects_missing_concept_input(tmp_path: Path) -> None:
    provider = _Provider()

    with pytest.raises(WorkflowInputError, match="concept"):
        prepare_concept_to_portrait(
            _manifest("concept_to_portrait", (SourceSpec(kind="text", ref="red knight"),)),
            None,
            provider,
            tmp_path / "workspace",
        )


def test_concept_workflow_does_not_accept_approved_portrait_as_concept_input(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    save_png(workspace / "submitted" / "approved.png", _portrait_rgb())
    provider = _Provider()

    with pytest.raises(WorkflowInputError, match="concept"):
        prepare_concept_to_portrait(
            _manifest(
                "concept_to_portrait",
                (SourceSpec(kind="approved_portrait", ref="approved.png"),),
            ),
            None,
            provider,
            workspace,
        )

    assert provider.requests == []


def _approved_manifest(workflow: str, edit: EditSpec | None = None) -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow=workflow,
        provider="test-provider",
        sources=(SourceSpec(kind="approved_portrait", ref="hero.png"),),
        edit=edit,
    )


def test_expression_refine_rejects_missing_approved_portrait(tmp_path: Path) -> None:
    with pytest.raises(WorkflowInputError, match="approved portrait"):
        prepare_expression_refine(
            _approved_manifest("expression_refine"),
            None,
            _Provider(),
            tmp_path / "workspace",
        )


def test_expression_refine_requires_image_to_image_capability(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    write_valid_package(workspace / "submitted")

    class _NoImageProvider:
        id = "no-image"
        capabilities = CapabilitySet(capabilities=frozenset())

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            raise AssertionError("must refuse before generating")

    with pytest.raises(ProviderRefusal, match="image_to_image"):
        prepare_expression_refine(
            _approved_manifest("expression_refine"),
            None,
            _NoImageProvider(),
            workspace,
        )


def test_expression_refine_requires_matching_submitted_palette(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    write_valid_package(workspace / "submitted")
    (workspace / "submitted" / "hero.pal").unlink()
    provider = _Provider()

    with pytest.raises(WorkflowInputError, match="matching JASC palette"):
        prepare_expression_refine(
            _approved_manifest("expression_refine"),
            None,
            provider,
            workspace,
        )

    assert provider.requests == []


def test_expression_refine_rejects_incomplete_expression_roles(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    write_valid_package(workspace / "submitted")

    class _IncompleteProvider(_Provider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            return GenResponse(ok=True, artifacts=())

    with pytest.raises(WorkflowFailure, match="complete expression roles"):
        prepare_expression_refine(
            _approved_manifest("expression_refine"),
            None,
            _IncompleteProvider(),
            workspace,
        )


@pytest.mark.parametrize(
    ("mask", "message"),
    [
        (None, "mask must be"),
        (np.full((80, 96, 3), 128, dtype=np.uint8), "black-and-white"),
        (np.zeros((40, 96, 3), dtype=np.uint8), "mask shape"),
    ],
)
def test_masked_variant_rejects_invalid_submitted_mask(
    tmp_path: Path,
    mask: np.ndarray | None,
    message: str,
) -> None:
    workspace = tmp_path / "workspace"
    write_valid_package(workspace / "submitted")
    if mask is not None:
        save_png(workspace / "submitted" / "mask.png", mask)

    with pytest.raises(WorkflowInputError, match=message):
        prepare_masked_variant(
            _approved_manifest("masked_variant", EditSpec(mask_path="mask.png")),
            None,
            _Provider(),
            workspace,
        )


def test_masked_variant_rejects_protected_region_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    write_valid_package(workspace / "submitted")
    mask = np.zeros((80, 96, 3), dtype=np.uint8)
    mask[48:64, 40:56] = 255
    save_png(workspace / "submitted" / "mask.png", mask)

    class _ProtectedRegionProvider(_Provider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            output = workspace / "generated" / "variant.png"
            edited = np.full((80, 96, 3), (200, 40, 40), dtype=np.uint8)
            save_png(output, edited)
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="variant",
                        path="generated/variant.png",
                        sha256=sha256_file(output),
                        media_type="image/png",
                    ),
                ),
            )

    with pytest.raises(WorkflowFailure, match="PROTECTED_REGION_CHANGED"):
        prepare_masked_variant(
            _approved_manifest(
                "masked_variant",
                EditSpec(
                    mask_path="mask.png",
                    protected_regions=(Region(x=40, y=48, w=16, h=16, label="face"),),
                ),
            ),
            None,
            _ProtectedRegionProvider(),
            workspace,
        )


def test_masked_variant_rejects_wrong_sized_provider_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    write_valid_package(workspace / "submitted")
    save_png(workspace / "submitted" / "mask.png", np.zeros((80, 96, 3), dtype=np.uint8))

    class _WrongSizedProvider(_Provider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            output = workspace / "generated" / "variant.png"
            save_png(output, np.zeros((40, 96, 3), dtype=np.uint8))
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="variant",
                        path="generated/variant.png",
                        sha256=sha256_file(output),
                        media_type="image/png",
                    ),
                ),
            )

    with pytest.raises(WorkflowFailure, match="invalid variant image"):
        prepare_masked_variant(
            _approved_manifest("masked_variant", EditSpec(mask_path="mask.png")),
            None,
            _WrongSizedProvider(),
            workspace,
        )
