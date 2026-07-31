from __future__ import annotations

from fecreator.assets.dialogue_background.plugin import DialogueBackgroundPlugin
from fecreator.assets.portrait.plugin import PortraitPlugin
from fecreator.core.registry import ASSET_REGISTRY


def register_builtin_assets() -> None:
    if "portrait" not in ASSET_REGISTRY.ids():
        ASSET_REGISTRY.register("portrait", PortraitPlugin())
    if "dialogue_background" not in ASSET_REGISTRY.ids():
        ASSET_REGISTRY.register("dialogue_background", DialogueBackgroundPlugin())


register_builtin_assets()
