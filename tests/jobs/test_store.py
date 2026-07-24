from __future__ import annotations

import json

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs.model import JobState
from fecreator.jobs.store import JobStore


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


def test_resume_from_fresh_store_instance(data_root) -> None:
    first = JobStore(data_root)
    job = first.create(_manifest())
    job.state = JobState.PLANNING

    first.save(job)

    reopened = JobStore(data_root).load(job.id)
    assert reopened.state is JobState.PLANNING
    assert reopened.manifest.content_hash() == _manifest().content_hash()


def test_save_does_not_rewrite_manifest_snapshot(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    manifest_path = data_root / "jobs" / job.id / "manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    job.state = JobState.PLANNING

    store.save(job)

    assert manifest_path.read_text(encoding="utf-8") == original


def test_interrupted_tmp_does_not_corrupt(data_root) -> None:
    store = JobStore(data_root)
    job = store.create(_manifest())
    (data_root / "jobs" / job.id / "job.json.tmp").write_text("garbage", encoding="utf-8")
    job.state = JobState.PLANNING

    store.save(job)

    assert JobStore(data_root).load(job.id).state is JobState.PLANNING


def test_list_jobs(data_root) -> None:
    store = JobStore(data_root)
    first = store.create(_manifest())
    second = store.create(_manifest())

    assert set(store.list_jobs()) == {first.id, second.id}
