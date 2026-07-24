from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ReferencePack(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    path: Path
