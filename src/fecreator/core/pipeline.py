from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from fecreator.contracts.result import StageResult


class PipelineContext(BaseModel):
    job_id: str
    workspace: Path
    cancelled: bool = False


@runtime_checkable
class PipelineStep(Protocol):
    name: str

    def run(self, ctx: PipelineContext) -> StageResult: ...


class Pipeline:
    def run(self, steps: Sequence[PipelineStep], ctx: PipelineContext) -> tuple[StageResult, ...]:
        results: list[StageResult] = []
        for step in steps:
            if ctx.cancelled:
                break
            result = step.run(ctx)
            results.append(result)
            if not result.ok:
                break
        return tuple(results)
