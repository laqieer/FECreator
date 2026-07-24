from __future__ import annotations

from PIL import Image

from fecreator.contracts.capabilities import Capability
from fecreator.providers.base import GenRequest
from fecreator.providers.manual import ManualProvider


def test_capabilities_include_masked_edit() -> None:
    assert Capability.MASKED_EDIT in ManualProvider().capabilities.capabilities


def test_generate_picks_up_submitted_files(tmp_path) -> None:
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    Image.new("RGB", (1, 1), color=(0, 0, 255)).save(submitted / "neutral.png", format="PNG")

    response = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is True
    assert [artifact.role for artifact in response.artifacts] == ["neutral"]
    assert response.artifacts[0].path == "submitted/neutral.png"
    assert len(response.artifacts[0].sha256) == 64


def test_generate_empty_is_not_ok(tmp_path) -> None:
    response = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is False


def test_generate_inferrs_jpeg_media_type(tmp_path) -> None:
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(submitted / "neutral.jpg", format="JPEG")

    response = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is True
    assert response.artifacts[0].media_type == "image/jpeg"


def test_generate_rejects_non_image_submission(tmp_path) -> None:
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    (submitted / "notes.txt").write_text("not an image", encoding="utf-8")

    response = ManualProvider().generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is False
    assert response.artifacts == ()
    assert response.diagnostics[0].code == "MANUAL_UNSUPPORTED_SUBMISSION"
