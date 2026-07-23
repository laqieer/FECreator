from __future__ import annotations

from fecreator.contracts.result import Artifact, JobResult, StageResult


def test_artifact_and_stage_result() -> None:
    artifact = Artifact(role="export", path="out/x.png", sha256="0" * 64, media_type="image/png")
    stage_result = StageResult(stage="export", ok=True, artifacts=(artifact,))

    assert stage_result.artifacts[0].path == "out/x.png"


def test_job_result_defaults() -> None:
    job_result = JobResult(job_id="j1", ok=False)

    assert job_result.artifacts == ()
    assert job_result.lineage_id is None
