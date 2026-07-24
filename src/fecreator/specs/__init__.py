from __future__ import annotations

from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.fe_gba_portrait import FEGbaPortraitStandardSpec


def _register(spec_id: str, spec: object) -> None:
    if spec_id not in set(SPEC_REGISTRY.ids()):
        SPEC_REGISTRY.register(spec_id, spec)


_register("fe-gba-portrait-standard", FEGbaPortraitStandardSpec())
