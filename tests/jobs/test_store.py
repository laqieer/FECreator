from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs import store as store_module
from fecreator.jobs.approvals import ApprovalStore
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobState
from fecreator.jobs.store import JobCorruptionError, JobStore, RevisionConflictError


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
    original = store_module._write_json_atomic_unlocked

    def fake_write_json_atomic(path, obj) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("boom")
        original(path, obj)

    monkeypatch.setattr(store_module, "_write_json_atomic_unlocked", fake_write_json_atomic)

    with pytest.raises(OSError, match="boom"):
        JobStore(data_root).create(_manifest())

    assert JobStore(data_root).list_jobs() == []


def test_list_jobs_ignores_staging_directories(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    staging_dir = data_root / "jobs" / ".tmp-orphan"
    staging_dir.mkdir(parents=True)
    (staging_dir / "manifest.json").write_text("{}", encoding="utf-8")

    assert set(store.list_jobs()) == {job.id}


def test_init_prunes_only_stale_staging_directories(data_root) -> None:
    jobs_dir = data_root / "jobs"
    jobs_dir.mkdir()
    stale = jobs_dir / ".tmp-stale"
    fresh = jobs_dir / ".tmp-fresh"
    stale.mkdir()
    fresh.mkdir()
    now = time.time()
    os.utime(stale, (now - 600, now - 600))
    os.utime(fresh, (now, now))

    JobStore(data_root)

    assert not stale.exists()
    assert fresh.exists()


def test_init_keeps_stale_staging_directory_with_active_lock(data_root, tmp_path) -> None:
    jobs_dir = data_root / "jobs"
    staging = jobs_dir / ".tmp-active"
    staging.mkdir(parents=True)
    now = time.time() - 600
    os.utime(staging, (now, now))
    script = tmp_path / "hold_stage_lock.py"
    script.write_text(
        """
from __future__ import annotations

import sys
import time
from pathlib import Path

from fecreator.core.atomicio import _path_lock


target = Path(sys.argv[1])
ready = Path(sys.argv[2])
with _path_lock(target, timeout=5.0, poll_interval=0.01):
    ready.write_text("ready", encoding="utf-8")
    time.sleep(1.0)
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    ready = tmp_path / "ready.txt"
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = (
        src_dir if not env.get("PYTHONPATH") else f"{src_dir}{os.pathsep}{env['PYTHONPATH']}"
    )
    holder = subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(data_root / "jobs" / ".locks" / "staging-active"),
            str(ready),
        ],
        env=env,
    )
    try:
        deadline = time.time() + 5
        while not ready.exists():
            assert time.time() < deadline
            time.sleep(0.01)

        JobStore(data_root)
    finally:
        holder.wait(timeout=5)

    assert staging.exists()


def test_save_missing_job_does_not_create_visible_directory(data_root) -> None:
    store = JobStore(data_root)
    missing = Job(
        id="ghost",
        state=JobState.CREATED,
        manifest=_manifest(),
        revision=1,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )

    with pytest.raises(FileNotFoundError):
        store.save(missing, expected_revision=1)

    assert store.list_jobs() == []


def test_list_jobs_raises_for_visible_corruption(data_root) -> None:
    jobs_dir = data_root / "jobs"
    broken = jobs_dir / "broken"
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(JobCorruptionError):
        JobStore(data_root).list()


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
    original_read_json = store_module._read_json_unlocked
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

    def worker(job: Job) -> None:
        try:
            store.save(job, expected_revision=1)
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            errors.append(exc)

    monkeypatch.setattr(store_module, "_read_json_unlocked", fake_read_json)

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


def test_list_returns_jobs_sorted_by_id(data_root) -> None:
    store = JobStore(data_root)
    first = store.create(_manifest())
    second = store.create(_manifest())

    assert [job.id for job in store.list()] == sorted([first.id, second.id])


def test_unknown_job_reads_do_not_pollute_list_jobs(data_root) -> None:
    store = JobStore(data_root)
    healthy = store.create(_manifest())

    assert EventLog(data_root).read("missing-job") == []
    assert ApprovalStore(data_root).decisions("missing-job") == []

    assert store.list_jobs() == [healthy.id]


def test_load_raises_when_visible_job_id_does_not_match_payload(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    job_path = data_root / "jobs" / job.id / "job.json"
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    payload["id"] = "different-id"
    job_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(JobCorruptionError, match="job id"):
        store.load(job.id)
