from __future__ import annotations

from importlib import resources
from pathlib import Path


def web_dir() -> Path | None:
    try:
        target = resources.files("fecreator") / "_web"
    except ModuleNotFoundError:
        return None
    path = Path(str(target))
    return path if path.is_dir() else None
