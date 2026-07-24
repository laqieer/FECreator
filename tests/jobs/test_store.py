from __future__ import annotations

import json

import pytest

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs import store as store_module
from fecreator.jobs.model import JobState
from fecreator.jobs.store import JobStore, RevisionConflictError


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def test_create_persists_and_snapshots_manifest(data_root) -> None:
    store = JobStore(data_root)

    job = store.create(_manifest())

    assert job.state is JobState.CREATED
    assert job.revision == 1
    snap = json.loads((data_root / "jobs" / job.id / "manifest.json").read_text())
    assert snap["provider"] == "fake"


def test_create_rolls_back_failed_job_write(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = store_module.write_json_atomic

    def fake_write_json_atomic(path, obj) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("boom")
        original(path, obj)

    monkeypatch.setattr(store_module, "write_json_atomic", fake_write_json_atomic)

    with pytest.raises(OSError, match="boom"):
        JobStore(data_root).create(_manifest())

    jobs_dir = data_root / "jobs"
    assert not jobs_dir.exists() or list(jobs_dir.iterdir()) == []


def test_resume_from_fresh_store_instance(data_root) -> None:
    first = JobStore(data_root)
    job = first.create(_manifest())
    job.state = JobState.PLANNING

    first.save(job, expected_revision=1)

    reopened = JobStore(data_root).load(job.id)
    assert reopened.state is JobState.PLANNING
    assert reopened.revision == 2
    assert reopened.manifest.content_hash() == _manifest().content_hash()


def test_save_rejects_stale_revision(data_root) -> None:
    store = JobStore(data_root)
    fresh = store.create(_manifest())
    stale = store.load(fresh.id)
    fresh.state = JobState.PLANNING

    store.save(fresh, expected_revision=1)

    stale.state = JobState.PROCESSING
    with pytest.raises(RevisionConflictError):
        store.save(stale, expected_revision=1)


def test_save_does_not_rewrite_manifest_snapshot(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    manifest_path = data_root / "jobs" / job.id / "manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    job.state = JobState.PLANNING

    store.save(job, expected_revision=1)

    assert manifest_path.read_text(encoding="utf-8") == original


def test_interrupted_tmp_does_not_corrupt(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    (data_root / "jobs" / job.id / "job.json.tmp").write_text("garbage", encoding="utf-8")
    job.state = JobState.PLANNING

    store.save(job, expected_revision=1)

    assert JobStore(data_root).load(job.id).state is JobState.PLANNING


def test_list_jobs(data_root) -> None:
    store = JobStore(data_root)
    first = store.create(_manifest())
    second = store.create(_manifest())

    assert set(store.list_jobs()) == {first.id, second.id}
