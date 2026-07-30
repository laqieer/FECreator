from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.contracts.dialogue_background import DialogueBackgroundPackageManifest
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import ImageBudgetError, load_opaque_png_rgb

WIDTH = 240
HEIGHT = 160
_NON_OPAQUE_MESSAGE = "PNG contains non-opaque pixels"


def _within(package_dir: Path, path: Path) -> bool:
    try:
        root = package_dir.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return path.is_file() and not path.is_symlink() and resolved.parent == root


def _png_diagnostic(path: Path, exc: Exception) -> Diagnostic:
    if (
        isinstance(exc, ValueError)
        and isinstance(exc.__cause__, ValueError)
        and str(exc.__cause__) == _NON_OPAQUE_MESSAGE
    ):
        return error(
            "NON_OPAQUE_BACKGROUND",
            "background PNG must be fully opaque",
            where=path.name,
        )
    return error(
        "INVALID_BACKGROUND_PNG",
        "background must be a supported opaque PNG",
        where=path.name,
    )


def validate_package(package_dir: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not package_dir.is_dir():
        return [error("MISSING_BACKGROUND_PACKAGE", "package directory does not exist")]

    entries = sorted(package_dir.iterdir(), key=lambda path: path.name)
    safe_entries: list[Path] = []
    for entry in entries:
        if not _within(package_dir, entry):
            diagnostics.append(
                error(
                    "UNSAFE_BACKGROUND_PACKAGE_ENTRY",
                    "package entries must be regular files",
                    where=entry.name,
                )
            )
            continue
        safe_entries.append(entry)

    pngs = [entry for entry in safe_entries if entry.suffix.casefold() == ".png"]
    manifests = [entry for entry in safe_entries if entry.name.endswith(".manifest.json")]
    expected = {path.name for path in (*pngs, *manifests)}
    for entry in entries:
        if entry.name not in expected:
            diagnostics.append(
                error(
                    "UNEXPECTED_BACKGROUND_PACKAGE_ENTRY",
                    "dialogue background packages contain only PNG and manifest files",
                    where=entry.name,
                )
            )

    if len(pngs) != 1:
        diagnostics.append(error("MISSING_BACKGROUND_PNG", "package must contain one PNG"))
    if len(manifests) != 1:
        diagnostics.append(
            error("MISSING_BACKGROUND_MANIFEST", "package must contain one manifest")
        )
    if len(pngs) != 1 or len(manifests) != 1:
        return diagnostics

    png_path = pngs[0]
    manifest_path = manifests[0]
    try:
        manifest = DialogueBackgroundPackageManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        diagnostics.append(
            error(
                "INVALID_BACKGROUND_MANIFEST",
                "dialogue background manifest is malformed",
                where=manifest_path.name,
            )
        )
        return diagnostics

    if png_path.name != f"{manifest.name}.png" or (
        manifest_path.name != f"{manifest.name}.manifest.json"
    ):
        diagnostics.append(
            error(
                "BACKGROUND_NAME_MISMATCH",
                "package filenames must match manifest.name",
                where=manifest_path.name,
            )
        )

    try:
        rgb, _mode = load_opaque_png_rgb(png_path)
    except (ImageBudgetError, ValueError) as exc:
        diagnostics.append(_png_diagnostic(png_path, exc))
        return diagnostics

    if rgb.shape != (HEIGHT, WIDTH, 3):
        diagnostics.append(
            error(
                "INVALID_BACKGROUND_DIMENSIONS",
                f"background must be exactly {WIDTH}x{HEIGHT}",
                where=png_path.name,
            )
        )
    if sha256_file(png_path) != manifest.png_sha256:
        diagnostics.append(
            error(
                "BACKGROUND_HASH_MISMATCH",
                "manifest PNG hash does not match the package image",
                where=png_path.name,
            )
        )
    return diagnostics
