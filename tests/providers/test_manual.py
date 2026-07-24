from __future__ import annotations

from fecreator.contracts.capabilities import Capability
from fecreator.providers.base import GenRequest
from fecreator.providers.manual import ManualProvider


def test_capabilities_include_masked_edit() -> None:
    assert Capability.MASKED_EDIT in ManualProvider().capabilities.capabilities


def test_generate_picks_up_submitted_files(tmp_path) -> None:
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    (submitted / "neutral.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    response = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is True
    assert [artifact.role for artifact in response.artifacts] == ["neutral"]
    assert response.artifacts[0].path == "submitted/neutral.png"
    assert len(response.artifacts[0].sha256) == 64


def test_generate_empty_is_not_ok(tmp_path) -> None:
    response = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is False
