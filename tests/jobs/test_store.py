from __future__ import annotations

import json
import threading

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


def test_list_jobs_ignores_staging_directories(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    staging_dir = data_root / "jobs" / ".tmp-orphan"
    staging_dir.mkdir(parents=True)
    (staging_dir / "manifest.json").write_text("{}", encoding="utf-8")

    assert set(store.list_jobs()) == {job.id}


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


def test_save_serializes_concurrent_revision_checks(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = JobStore(data_root)
    first_job = store.create(_manifest())
    second_job = store.load(first_job.id)
    first_job.state = JobState.PLANNING
    second_job.state = JobState.PROCESSING
    first_read_started = threading.Event()
    release_first_writer = threading.Event()
    original_read_json = store_module.read_json
    read_count = 0
    count_lock = threading.Lock()
    errors: list[Exception] = []
    job_path = data_root / "jobs" / first_job.id / "job.json"

    def fake_read_json(path):
        nonlocal read_count
        payload = original_read_json(path)
        if path == job_path:
            with count_lock:
                read_count += 1
                current_read = read_count
            if current_read == 1:
                first_read_started.set()
                if not release_first_writer.wait(timeout=5):
                    raise TimeoutError("timed out waiting to release writer")
        return payload

    def worker(job) -> None:
        try:
            store.save(job, expected_revision=1)
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            errors.append(exc)

    monkeypatch.setattr(store_module, "read_json", fake_read_json)

    first = threading.Thread(target=worker, args=(first_job,))
    second = threading.Thread(target=worker, args=(second_job,))
    first.start()
    assert first_read_started.wait(timeout=5)
    second.start()
    release_first_writer.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert sum(isinstance(exc, RevisionConflictError) for exc in errors) == 1
    assert store.load(first_job.id).revision == 2


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
