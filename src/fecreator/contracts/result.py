"""PROVISIONAL bootstrap contract shim.

The contracts task must preserve ``stage`` and ``ok`` while extending StageResult
only with defaulted fields.
"""

from __future__ import annotations

from pydantic import BaseModel


class StageResult(BaseModel):
    stage: str
    ok: bool
