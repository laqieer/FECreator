from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        frontend_entrypoint = Path(self.root, "src", "fecreator", "_web", "index.html")
        if version == "editable":
            frontend_entrypoint.parent.mkdir(parents=True, exist_ok=True)
            return

        if frontend_entrypoint.is_file():
            return

        message = (
            "Missing required frontend asset: src/fecreator/_web/index.html. "
            "Run `npm ci && npm run -w @laqieer/fecreator-web build` from the repository root "
            "before `python -m build`."
        )
        raise RuntimeError(message)
