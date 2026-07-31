from __future__ import annotations

from pathlib import Path

from fecreator.contracts.diagnostics import Diagnostic
from fecreator.specs.fire_emblem.gba.dialogue_background_source.validation import (
    validate_package,
)


class Fe8DialogueBackgroundSource240x160:
    id = "fe8-dialogue-background-source-240x160"

    def validate(self, package_dir: Path) -> list[Diagnostic]:
        return validate_package(package_dir)
