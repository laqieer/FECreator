from __future__ import annotations

from fecreator.providers.base import GenRequest
from fecreator.providers.fake import FakeProvider


def test_generate_is_deterministic(tmp_path) -> None:
    request = GenRequest(
        workflow="text_to_portrait",
        prompt="brave knight",
        params={"width": 96, "height": 80},
    )

    first = FakeProvider().generate(request, tmp_path / "a")
    second = FakeProvider().generate(request, tmp_path / "b")

    assert first.ok is True
    assert first.artifacts[0].sha256 == second.artifacts[0].sha256
    assert first.artifacts[0].path == "generated/neutral.png"


def test_different_prompt_differs(tmp_path) -> None:
    first = FakeProvider().generate(GenRequest(workflow="w", prompt="a"), tmp_path / "1")
    second = FakeProvider().generate(GenRequest(workflow="w", prompt="b"), tmp_path / "2")

    assert first.artifacts[0].sha256 != second.artifacts[0].sha256
