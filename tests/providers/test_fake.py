from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import fecreator.providers.fake as fake_module
from fecreator.providers.base import GenRequest, ProviderRefusal
from fecreator.providers.fake import FakeProvider


def _install_imaging_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    imaging_module = types.ModuleType("fecreator.imaging")
    io_module = types.ModuleType("fecreator.imaging.io")

    def save_png(path: Path, rgb: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb, "RGB").save(path, format="PNG")

    io_module.save_png = save_png
    monkeypatch.setitem(sys.modules, "fecreator.imaging", imaging_module)
    monkeypatch.setitem(sys.modules, "fecreator.imaging.io", io_module)


def test_generate_is_deterministic(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_imaging_stub(monkeypatch)
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


def test_different_prompt_differs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_imaging_stub(monkeypatch)
    first = FakeProvider().generate(GenRequest(workflow="w", prompt="a"), tmp_path / "1")
    second = FakeProvider().generate(GenRequest(workflow="w", prompt="b"), tmp_path / "2")

    assert first.artifacts[0].sha256 != second.artifacts[0].sha256


def test_generate_refuses_non_positive_dimensions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_imaging_stub(monkeypatch)

    with pytest.raises(ProviderRefusal):
        FakeProvider().generate(
            GenRequest(workflow="w", prompt="a", params={"width": 0, "height": 80}),
            tmp_path / "bad",
        )


def test_generate_refuses_requests_over_pixel_budget(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_imaging_stub(monkeypatch)

    with pytest.raises(ProviderRefusal):
        FakeProvider().generate(
            GenRequest(workflow="w", prompt="a", params={"width": 5000, "height": 5000}),
            tmp_path / "huge",
        )


def test_load_save_png_refuses_missing_imaging_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_missing(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(fake_module, "import_module", _raise_missing)

    with pytest.raises(
        ProviderRefusal,
        match="fake provider requires fecreator.imaging.io.save_png",
    ) as excinfo:
        fake_module._load_save_png()

    assert isinstance(excinfo.value.__cause__, ModuleNotFoundError)


def test_load_save_png_refuses_missing_callable_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fake_module,
        "import_module",
        lambda name: types.SimpleNamespace(save_png=None),
    )

    with pytest.raises(
        ProviderRefusal,
        match="fake provider requires fecreator.imaging.io.save_png",
    ) as excinfo:
        fake_module._load_save_png()

    assert isinstance(excinfo.value.__cause__, TypeError)
