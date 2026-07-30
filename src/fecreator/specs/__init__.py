from __future__ import annotations

from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.fire_emblem.gba.dialogue_background_source.spec import (
    Fe8DialogueBackgroundSource240x160,
)
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard

if "fe8-dialogue-background-source-240x160" not in SPEC_REGISTRY.ids():
    SPEC_REGISTRY.register(
        "fe8-dialogue-background-source-240x160",
        Fe8DialogueBackgroundSource240x160(),
    )

if "fe-gba-portrait-standard" not in SPEC_REGISTRY.ids():
    SPEC_REGISTRY.register("fe-gba-portrait-standard", FeGbaPortraitStandard())
