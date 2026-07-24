from __future__ import annotations

from pathlib import Path

from fecreator.contracts.diagnostics import Diagnostic, error

_SHEET_NAMES = frozenset({"portrait.png", "sheet.png", "portrait_sheet.png"})


class FEGbaPortraitStandardSpec:
    id = "fe-gba-portrait-standard"

    def validate(self, package_dir: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        if not package_dir.exists() or not any(
            f.name in _SHEET_NAMES or f.suffix == ".png"
            for f in package_dir.iterdir()
            if f.is_file()
        ):
            diags.append(
                error(
                    "MISSING_SHEET",
                    "Portrait sprite sheet is missing from the package directory.",
                    where=str(package_dir),
                )
            )
        return diags
