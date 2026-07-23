from pathlib import Path

from fecreator.contracts.result import StageResult
from fecreator.core.pipeline import Pipeline, PipelineContext


class _Step:
    def __init__(self, name: str, ok: bool = True) -> None:
        self.name = name
        self._ok = ok

    def run(self, ctx: PipelineContext) -> StageResult:
        return StageResult(stage=self.name, ok=self._ok)


def test_pipeline_runs_all_steps(tmp_path: Path) -> None:
    ctx = PipelineContext(job_id="j1", workspace=tmp_path)
    results = Pipeline().run([_Step("a"), _Step("b")], ctx)
    assert [r.stage for r in results] == ["a", "b"]


def test_pipeline_stops_after_failure(tmp_path: Path) -> None:
    ctx = PipelineContext(job_id="j1", workspace=tmp_path)
    results = Pipeline().run([_Step("a", ok=False), _Step("b")], ctx)
    assert [r.stage for r in results] == ["a"]


def test_pipeline_respects_cancellation(tmp_path: Path) -> None:
    ctx = PipelineContext(job_id="j1", workspace=tmp_path, cancelled=True)
    results = Pipeline().run([_Step("a")], ctx)
    assert results == ()
