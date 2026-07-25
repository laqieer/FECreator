from __future__ import annotations

from fecreator.assets.portrait.plugin import PortraitPlugin
from fecreator.core.registry import ASSET_REGISTRY

if "portrait" not in ASSET_REGISTRY.ids():
    ASSET_REGISTRY.register("portrait", PortraitPlugin())
