from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fecreator.assets.portrait.workflows import (
    WorkflowInputError,
    prepare_concept_to_portrait,
    prepare_text_to_portrait,
)
from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.lineage import Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import save_png
from fecreator.providers.base import GenRequest, GenResponse


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
