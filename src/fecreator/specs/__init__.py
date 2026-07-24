from __future__ import annotations

from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

if "fe-gba-portrait-standard" not in SPEC_REGISTRY.ids():
    SPEC_REGISTRY.register("fe-gba-portrait-standard", FeGbaPortraitStandard())
