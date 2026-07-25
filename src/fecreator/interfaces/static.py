from __future__ import annotations

from importlib import resources
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from fecreator.core.paths import is_contained

_REPARSE_POINT = 0x400

_MISSING_WEB_ASSETS_MESSAGE = (
    "Packaged web assets are unavailable. "
    "Run `npm run -w @laqieer/fecreator-web build` to build them."
)


def web_dir() -> Path | None:
    try:
        package_root = Path(str(resources.files("fecreator")))
    except ModuleNotFoundError:
        return None

    path = package_root / "_web"
    if _is_unsafe_asset_dir(path, package_root):
        return None
    return path


def _is_unsafe_asset_dir(path: Path, package_root: Path) -> bool:
    if not path.is_dir() or not (path / "index.html").is_file():
        return True
    if path.is_symlink() or _is_reparse_point(path):
        return True
    return not is_contained(package_root, path)


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _REPARSE_POINT)


def mount_static(api: FastAPI) -> None:
    directory = web_dir()
    if directory is None:

        @api.get("/", include_in_schema=False)
        def web_assets_unavailable() -> PlainTextResponse:
            return PlainTextResponse(
                _MISSING_WEB_ASSETS_MESSAGE,
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return

    api.mount("/", StaticFiles(directory=str(directory), html=True), name="web")
