from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import numpy as np

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal

_DEFAULT_HEIGHT = 80
_DEFAULT_WIDTH = 96
_MAX_DIMENSION = 4096
_MAX_PIXELS = 8_000_000


class _SavePng(Protocol):
    def __call__(self, path: Path, rgb: np.ndarray) -> None: ...


class FakeProvider:
    id = "fake"
    capabilities = CapabilitySet(capabilities=frozenset(Capability))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        digest = hashlib.sha256((request.prompt or "").encode("utf-8")).digest()
        width = _coerce_positive_dimension(request.params.get("width"), _DEFAULT_WIDTH, "width")
        height = _coerce_positive_dimension(request.params.get("height"), _DEFAULT_HEIGHT, "height")
        if width > _MAX_DIMENSION or height > _MAX_DIMENSION or width * height > _MAX_PIXELS:
            raise ProviderRefusal("fake provider dimensions exceed resource budget")

        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        rgb[:, :] = (digest[0], digest[1], digest[2])

        output = workspace / "generated" / "neutral.png"
        _load_save_png()(output, rgb)

        artifact = Artifact(
            role="neutral",
            path="generated/neutral.png",
            sha256=sha256_file(output),
            media_type="image/png",
        )
        return GenResponse(ok=True, artifacts=(artifact,), model="fake-1", seed=request.seed or 0)


def _coerce_positive_dimension(
    value: str | int | float | bool | None,
    default: int,
    label: str,
) -> int:
    if value is None:
        coerced = default
    elif isinstance(value, bool):
        raise ProviderRefusal(f"fake provider requires positive integer {label}")
    elif isinstance(value, int):
        coerced = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ProviderRefusal(f"fake provider requires positive integer {label}")
        coerced = int(value)
    elif isinstance(value, str):
        if not value.isdigit():
            raise ProviderRefusal(f"fake provider requires positive integer {label}")
        coerced = int(value)
    else:
        raise ProviderRefusal(f"fake provider requires positive integer {label}")

    if coerced <= 0:
        raise ProviderRefusal(f"fake provider requires positive integer {label}")
    return coerced


def _load_save_png() -> _SavePng:
    try:
        module = import_module("fecreator.imaging.io")
    except ModuleNotFoundError as exc:
        raise ProviderRefusal("fake provider requires fecreator.imaging.io.save_png") from exc
    save_png = getattr(module, "save_png", None)
    if not callable(save_png):
        raise ProviderRefusal(
            "fake provider requires fecreator.imaging.io.save_png"
        ) from TypeError(
            "save_png is missing or not callable",
        )
    return cast(_SavePng, save_png)
