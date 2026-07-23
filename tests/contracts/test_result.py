from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.result import Artifact, JobResult, StageResult


def test_artifact_and_stage_result() -> None:
    artifact = Artifact(role="export", path="out/x.png", sha256="0" * 64, media_type="image/png")
    stage_result = StageResult(stage="export", ok=True, artifacts=(artifact,))

    assert stage_result.artifacts[0].path == "out/x.png"


def test_job_result_defaults() -> None:
    job_result = JobResult(job_id="j1", ok=False)

    assert job_result.artifacts == ()
    assert job_result.lineage_id is None


def test_stage_result_metrics_are_immutable() -> None:
    stage_result = StageResult(stage="export", ok=True, metrics={"score": 0.5})

    with pytest.raises(TypeError):
        stage_result.metrics["other"] = 1.0


def test_stage_result_metrics_serialize_as_json_object() -> None:
    stage_result = StageResult(stage="export", ok=True, metrics={"score": 0.5})

    assert stage_result.model_dump(mode="json")["metrics"] == {"score": 0.5}


def test_stage_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StageResult(stage="export", ok=True, unexpected="value")
