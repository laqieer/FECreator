from __future__ import annotations

from pathlib import Path

import pytest

from fecreator.contracts.diagnostics import error
from fecreator.contracts.result import Artifact
from fecreator.contracts.review import CandidateSnapshot
from fecreator.jobs.candidates import CandidateCorruptionError, CandidateStore


def _artifact(name: str, sha: str) -> Artifact:
    return Artifact(
        role="concept_art",
        path=f"workspace/{name}.png",
        sha256=sha * 64,
        media_type="image/png",
    )


def _candidate_snapshot(job_id: str, *, lineage_id: str = "asset-1") -> CandidateSnapshot:
    return CandidateSnapshot(
        job_id=job_id,
        lineage_id=lineage_id,
        artifacts=(_artifact("neutral", "a"),),
        diagnostics=(error("CANDIDATE_WARN", "synthetic warning"),),
        metrics={"score": 0.95},
        created_at="2026-07-26T00:00:00+00:00",
    )


def test_create_is_immutable_and_rejects_second_create(data_root: Path) -> None:
    store = CandidateStore(data_root)
    snapshot = _candidate_snapshot(job_id="job-1")

    saved = store.create(snapshot)

    assert saved == snapshot
    assert store.load("job-1") == snapshot
    with pytest.raises(TypeError):
        saved.metrics["score"] = 0.1
    with pytest.raises(FileExistsError):
        store.create(snapshot)


def test_load_raises_for_corrupt_visible_candidate(data_root: Path) -> None:
    store = CandidateStore(data_root)
    snapshot = _candidate_snapshot(job_id="job-1")
    store.create(snapshot)
    (data_root / "jobs" / "job-1" / "candidate" / "candidate.json").write_text(
        "{not-json",
        encoding="utf-8",
    )

    with pytest.raises(CandidateCorruptionError, match="corrupt"):
        store.load("job-1")
