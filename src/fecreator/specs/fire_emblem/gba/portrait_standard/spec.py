from __future__ import annotations

from pathlib import Path

from fecreator.contracts.diagnostics import Diagnostic
from fecreator.specs.fire_emblem.gba.portrait_standard.validation import validate_package


class FeGbaPortraitStandard:
    id = "fe-gba-portrait-standard"

    def validate(self, package_dir: Path) -> list[Diagnostic]:
        return validate_package(package_dir)
