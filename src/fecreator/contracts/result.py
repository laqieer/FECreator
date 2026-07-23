from __future__ import annotations

from pydantic import BaseModel


class StageResult(BaseModel):
    stage: str
    ok: bool
