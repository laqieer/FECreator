from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from fecreator.contracts.diagnostics import Diagnostic


@runtime_checkable
class TargetSpec(Protocol):
    id: str

    def validate(self, package_dir: Path) -> list[Diagnostic]: ...
