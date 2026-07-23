from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    data_root: Path
    allow_remote_upload: bool = False


def get_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    if "FECREATOR_DATA_ROOT" not in env:
        raise KeyError("FECREATOR_DATA_ROOT is required")
    return Settings(
        host=env.get("FECREATOR_HOST", "127.0.0.1"),
        port=int(env.get("FECREATOR_PORT", "8765")),
        data_root=Path(env["FECREATOR_DATA_ROOT"]),
        allow_remote_upload=env.get("FECREATOR_ALLOW_REMOTE_UPLOAD", "false").lower() == "true",
    )
