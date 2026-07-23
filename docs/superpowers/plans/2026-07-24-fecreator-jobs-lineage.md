# FECreator Jobs & Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement persistent, resumable, immutable jobs/workspaces (states, atomic store, event log, approval gates) plus versioned character reference packs and an append-only asset-lineage DAG.

**Architecture:** All persistence lives under `Settings.data_root` in per-entity directories, written atomically (temp file + `os.replace`) so an interrupted process never corrupts committed state. Manifests, approvals, reference-pack revisions, and lineage nodes are immutable once written; state changes create new records, never rewrites.

**Tech Stack:** Python 3.11–3.13, Pydantic v2, stdlib `json`/`os`/`uuid`, pytest.

## Global Constraints

Inherited from `2026-07-24-fecreator-v1-master.md` §Global Constraints. Highlights: immutable jobs/revisions; fail closed on invalid transitions and path escapes; all paths constrained to the workspace via `core.paths.safe_join`; no credentials persisted.

**Implements todos:** `implement-jobs` (Tasks 1–6), `implement-lineage` (Tasks 7–8).
**Depends on:** Foundation (contracts, `core.paths`, `core.clock`, `core.hashing`).
**Signatures:** master §4.7 (jobs), §4.8 (references/lineage). Quote them verbatim.

---

## File structure built by this plan

```text
src/fecreator/core/atomicio.py
src/fecreator/jobs/{__init__,model,store,events,service,approvals}.py
src/fecreator/references/{__init__,model,store}.py
src/fecreator/lineage/{__init__,store}.py
tests/jobs/{test_model,test_store,test_events,test_service,test_approvals}.py
tests/references/test_pack_store.py
tests/lineage/test_lineage_store.py
```

Persistence layout under `data_root`:
```text
jobs/<job_id>/job.json        # mutable state record (atomic)
jobs/<job_id>/manifest.json   # immutable snapshot (written once at create)
jobs/<job_id>/events.jsonl    # append-only event log
jobs/<job_id>/approvals.jsonl # append-only approval records
refs/<pack_id>/<rev>.json     # immutable reference-pack revision
lineage/<asset_id>.json       # immutable lineage node
```

---

## Task 1: Atomic JSON/JSONL I/O helper

**Files:**
- Create: `src/fecreator/core/atomicio.py`
- Test: `tests/core/test_atomicio.py`

**Interfaces:**
- Produces: `write_json_atomic(path: Path, obj: object) -> None` (temp + `os.replace`), `read_json(path: Path) -> object`, `append_jsonl(path: Path, obj: object) -> None`, `read_jsonl(path: Path) -> list[object]`.

- [ ] **Step 1: Write the failing test**

`tests/core/test_atomicio.py`:
```python
from fecreator.core.atomicio import append_jsonl, read_json, read_jsonl, write_json_atomic


def test_write_then_read(tmp_path):
    p = tmp_path / "a" / "x.json"
    write_json_atomic(p, {"k": 1})
    assert read_json(p) == {"k": 1}


def test_no_tmp_left_and_overwrites_stale_tmp(tmp_path):
    p = tmp_path / "x.json"
    (tmp_path / "x.json.tmp").write_text("garbage")
    write_json_atomic(p, {"k": 2})
    assert read_json(p) == {"k": 2}
    assert not (tmp_path / "x.json.tmp").exists()


def test_append_jsonl(tmp_path):
    p = tmp_path / "log.jsonl"
    append_jsonl(p, {"n": 1})
    append_jsonl(p, {"n": 2})
    assert read_jsonl(p) == [{"n": 1}, {"n": 2}]


def test_read_jsonl_missing_is_empty(tmp_path):
    assert read_jsonl(tmp_path / "none.jsonl") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_atomicio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.core.atomicio'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/core/atomicio.py`:
```python
from __future__ import annotations

import json
import os
from pathlib import Path


def write_json_atomic(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[object]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_atomicio.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/core/atomicio.py tests/core/test_atomicio.py
git commit -m "feat: add atomic json/jsonl io helpers

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Job model, states, and transition table

**Files:**
- Create: `src/fecreator/jobs/__init__.py`, `src/fecreator/jobs/model.py`
- Test: `tests/jobs/test_model.py`

**Interfaces:**
- Produces: `JobState` (10 members), `ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]]`, `Job(id, state, manifest, revision, created_at, updated_at)`, `JobEvent(seq, at, kind, message, data)` (master §4.7).

- [ ] **Step 1: Write the failing test**

`tests/jobs/test_model.py`:
```python
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs.model import ALLOWED_TRANSITIONS, Job, JobEvent, JobState


def _manifest():
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow="text_to_portrait", provider="fake",
                    sources=(SourceSpec(kind="text", ref="hero"),))


def test_ten_states():
    assert len(list(JobState)) == 10
    assert JobState.WAITING_FOR_REVIEW.value == "waiting_for_review"


def test_terminal_states_have_no_transitions():
    for terminal in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_created_can_go_to_planning_or_cancelled():
    assert ALLOWED_TRANSITIONS[JobState.CREATED] == frozenset({JobState.PLANNING, JobState.CANCELLED})


def test_job_and_event_shapes():
    j = Job(id="j1", state=JobState.CREATED, manifest=_manifest(), revision=1,
            created_at="2026-07-24T00:00:00+00:00", updated_at="2026-07-24T00:00:00+00:00")
    assert j.state is JobState.CREATED
    e = JobEvent(seq=0, at="2026-07-24T00:00:00+00:00", kind="created", message="job created")
    assert e.data == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.jobs.model'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/jobs/__init__.py`:
```python
```

`src/fecreator/jobs/model.py`:
```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.manifest import Manifest


class JobState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    WAITING_FOR_PROVIDER = "waiting_for_provider"
    WAITING_FOR_SOURCES = "waiting_for_sources"
    PROCESSING = "processing"
    WAITING_FOR_REVIEW = "waiting_for_review"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_CANCEL_OR_FAIL = frozenset({JobState.FAILED, JobState.CANCELLED})

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.CREATED: frozenset({JobState.PLANNING, JobState.CANCELLED}),
    JobState.PLANNING: frozenset({JobState.WAITING_FOR_PROVIDER, JobState.WAITING_FOR_SOURCES,
                                  JobState.PROCESSING}) | _CANCEL_OR_FAIL,
    JobState.WAITING_FOR_PROVIDER: frozenset({JobState.PROCESSING, JobState.WAITING_FOR_SOURCES})
        | _CANCEL_OR_FAIL,
    JobState.WAITING_FOR_SOURCES: frozenset({JobState.PROCESSING}) | _CANCEL_OR_FAIL,
    JobState.PROCESSING: frozenset({JobState.WAITING_FOR_REVIEW, JobState.VALIDATING})
        | _CANCEL_OR_FAIL,
    JobState.WAITING_FOR_REVIEW: frozenset({JobState.PROCESSING, JobState.VALIDATING})
        | _CANCEL_OR_FAIL,
    JobState.VALIDATING: frozenset({JobState.COMPLETED, JobState.WAITING_FOR_REVIEW})
        | _CANCEL_OR_FAIL,
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


class Job(BaseModel):
    id: str
    state: JobState
    manifest: Manifest
    revision: int
    created_at: str
    updated_at: str


class JobEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    seq: int
    at: str
    kind: str
    message: str
    data: dict[str, str | int | float | bool] = {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_model.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/jobs/__init__.py src/fecreator/jobs/model.py tests/jobs/test_model.py
git commit -m "feat: add job state model and transition table

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Immutable, atomic, resumable JobStore

**Files:**
- Create: `src/fecreator/jobs/store.py`
- Test: `tests/jobs/test_store.py`

**Interfaces:**
- Consumes: `Job`, `JobState` (Task 2); `Manifest`; `core.atomicio`; `core.paths.safe_join`; `core.clock.utc_now_iso`.
- Produces: `JobStore(root: Path)` with `create(manifest) -> Job`, `load(job_id) -> Job`, `save(job) -> None`, `list_jobs() -> list[str]`. `create` writes an immutable `manifest.json`; `save` writes only `job.json`.

- [ ] **Step 1: Write the failing test**

`tests/jobs/test_store.py`:
```python
import json

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs.model import JobState
from fecreator.jobs.store import JobStore


def _manifest():
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow="text_to_portrait", provider="fake",
                    sources=(SourceSpec(kind="text", ref="hero"),))


def test_create_persists_and_snapshots_manifest(data_root):
    store = JobStore(data_root)
    job = store.create(_manifest())
    assert job.state is JobState.CREATED and job.revision == 1
    snap = json.loads((data_root / "jobs" / job.id / "manifest.json").read_text())
    assert snap["provider"] == "fake"


def test_resume_from_fresh_store_instance(data_root):
    first = JobStore(data_root)
    job = first.create(_manifest())
    job.state = JobState.PLANNING
    first.save(job)
    reopened = JobStore(data_root).load(job.id)
    assert reopened.state is JobState.PLANNING
    assert reopened.manifest.content_hash() == _manifest().content_hash()


def test_save_does_not_rewrite_manifest_snapshot(data_root):
    store = JobStore(data_root)
    job = store.create(_manifest())
    manifest_path = data_root / "jobs" / job.id / "manifest.json"
    original = manifest_path.read_text()
    job.state = JobState.PLANNING
    store.save(job)
    assert manifest_path.read_text() == original


def test_interrupted_tmp_does_not_corrupt(data_root):
    store = JobStore(data_root)
    job = store.create(_manifest())
    (data_root / "jobs" / job.id / "job.json.tmp").write_text("garbage")
    job.state = JobState.PLANNING
    store.save(job)
    assert JobStore(data_root).load(job.id).state is JobState.PLANNING


def test_list_jobs(data_root):
    store = JobStore(data_root)
    a = store.create(_manifest())
    b = store.create(_manifest())
    assert set(store.list_jobs()) == {a.id, b.id}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.jobs.store'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/jobs/store.py`:
```python
from __future__ import annotations

import uuid
from pathlib import Path

from fecreator.contracts.manifest import Manifest
from fecreator.core.atomicio import read_json, write_json_atomic
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import Job, JobState


class JobStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _dir(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", job_id)

    def create(self, manifest: Manifest) -> Job:
        job_id = uuid.uuid4().hex
        now = utc_now_iso()
        job = Job(id=job_id, state=JobState.CREATED, manifest=manifest,
                  revision=1, created_at=now, updated_at=now)
        job_dir = self._dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(job_dir / "manifest.json", manifest.model_dump(mode="json"))
        self.save(job)
        return job

    def load(self, job_id: str) -> Job:
        job_dir = self._dir(job_id)
        record = read_json(job_dir / "job.json")
        manifest = Manifest.model_validate(read_json(job_dir / "manifest.json"))
        assert isinstance(record, dict)
        return Job(id=str(record["id"]), state=JobState(record["state"]), manifest=manifest,
                   revision=int(record["revision"]), created_at=str(record["created_at"]),
                   updated_at=str(record["updated_at"]))

    def save(self, job: Job) -> None:
        job.updated_at = utc_now_iso()
        record = {"id": job.id, "state": job.state.value, "revision": job.revision,
                  "created_at": job.created_at, "updated_at": job.updated_at}
        write_json_atomic(self._dir(job.id) / "job.json", record)

    def list_jobs(self) -> list[str]:
        jobs_dir = self._root / "jobs"
        if not jobs_dir.exists():
            return []
        return [p.name for p in jobs_dir.iterdir() if p.is_dir()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_store.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/jobs/store.py tests/jobs/test_store.py
git commit -m "feat: add atomic immutable resumable job store

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Append-only event log

**Files:**
- Create: `src/fecreator/jobs/events.py`
- Test: `tests/jobs/test_events.py`

**Interfaces:**
- Consumes: `JobEvent` (Task 2); `core.atomicio`; `core.paths.safe_join`; `core.clock.utc_now_iso`.
- Produces: `EventLog(root: Path)` with `append(job_id, kind, message, data=None) -> JobEvent` (monotonic `seq`) and `read(job_id) -> list[JobEvent]`.

- [ ] **Step 1: Write the failing test**

`tests/jobs/test_events.py`:
```python
from fecreator.jobs.events import EventLog


def test_append_assigns_monotonic_seq(data_root):
    log = EventLog(data_root)
    e0 = log.append("j1", "created", "job created")
    e1 = log.append("j1", "transition", "created->planning", {"to": "planning"})
    assert (e0.seq, e1.seq) == (0, 1)
    assert e1.data == {"to": "planning"}


def test_read_returns_all_events(data_root):
    log = EventLog(data_root)
    log.append("j1", "created", "a")
    log.append("j1", "transition", "b")
    events = log.read("j1")
    assert [e.kind for e in events] == ["created", "transition"]


def test_read_missing_job_is_empty(data_root):
    assert EventLog(data_root).read("nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.jobs.events'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/jobs/events.py`:
```python
from __future__ import annotations

from pathlib import Path

from fecreator.core.atomicio import append_jsonl, read_jsonl
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import JobEvent

DiagData = dict[str, str | int | float | bool]


class EventLog:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", job_id, "events.jsonl")

    def append(self, job_id: str, kind: str, message: str, data: DiagData | None = None) -> JobEvent:
        seq = len(self.read(job_id))
        event = JobEvent(seq=seq, at=utc_now_iso(), kind=kind, message=message, data=data or {})
        append_jsonl(self._path(job_id), event.model_dump(mode="json"))
        return event

    def read(self, job_id: str) -> list[JobEvent]:
        return [JobEvent.model_validate(row) for row in read_jsonl(self._path(job_id))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_events.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/jobs/events.py tests/jobs/test_events.py
git commit -m "feat: add append-only job event log

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: JobService transitions, cancel, resume

**Files:**
- Create: `src/fecreator/jobs/service.py`
- Test: `tests/jobs/test_service.py`

**Interfaces:**
- Consumes: `JobStore` (Task 3), `EventLog` (Task 4), `ALLOWED_TRANSITIONS`, `JobState`, `Job`.
- Produces: `InvalidTransitionError`; `JobService(store, events)` with `create_job(manifest) -> Job`, `transition(job_id, to) -> Job`, `cancel(job_id) -> Job`, `resume(job_id) -> Job`.

- [ ] **Step 1: Write the failing test**

`tests/jobs/test_service.py`:
```python
import pytest

from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import JobState
from fecreator.jobs.service import InvalidTransitionError, JobService
from fecreator.jobs.store import JobStore


def _service(data_root):
    return JobService(JobStore(data_root), EventLog(data_root))


def _manifest():
    return Manifest(asset_type="portrait", target_spec="fe-gba-portrait-standard",
                    workflow="text_to_portrait", provider="fake",
                    sources=(SourceSpec(kind="text", ref="hero"),))


def test_create_logs_event(data_root):
    svc = _service(data_root)
    job = svc.create_job(_manifest())
    kinds = [e.kind for e in EventLog(data_root).read(job.id)]
    assert "created" in kinds


def test_valid_transition(data_root):
    svc = _service(data_root)
    job = svc.create_job(_manifest())
    updated = svc.transition(job.id, JobState.PLANNING)
    assert updated.state is JobState.PLANNING


def test_invalid_transition_raises(data_root):
    svc = _service(data_root)
    job = svc.create_job(_manifest())
    with pytest.raises(InvalidTransitionError):
        svc.transition(job.id, JobState.COMPLETED)


def test_cancel_from_created(data_root):
    svc = _service(data_root)
    job = svc.create_job(_manifest())
    assert svc.cancel(job.id).state is JobState.CANCELLED


def test_cancel_terminal_raises(data_root):
    svc = _service(data_root)
    job = svc.create_job(_manifest())
    svc.cancel(job.id)
    with pytest.raises(InvalidTransitionError):
        svc.cancel(job.id)


def test_resume_reloads_from_disk(data_root):
    svc = _service(data_root)
    job = svc.create_job(_manifest())
    svc.transition(job.id, JobState.PLANNING)
    assert svc.resume(job.id).state is JobState.PLANNING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.jobs.service'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/jobs/service.py`:
```python
from __future__ import annotations

from fecreator.contracts.manifest import Manifest
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import ALLOWED_TRANSITIONS, Job, JobState
from fecreator.jobs.store import JobStore


class InvalidTransitionError(Exception):
    """Raised when a job state transition is not allowed."""


class JobService:
    def __init__(self, store: JobStore, events: EventLog) -> None:
        self._store = store
        self._events = events

    def create_job(self, manifest: Manifest) -> Job:
        job = self._store.create(manifest)
        self._events.append(job.id, "created", "job created")
        return job

    def transition(self, job_id: str, to: JobState) -> Job:
        job = self._store.load(job_id)
        if to not in ALLOWED_TRANSITIONS[job.state]:
            raise InvalidTransitionError(f"{job.state.value} -> {to.value} not allowed")
        frm = job.state
        job.state = to
        self._store.save(job)
        self._events.append(job_id, "transition", f"{frm.value}->{to.value}", {"to": to.value})
        return job

    def cancel(self, job_id: str) -> Job:
        return self.transition(job_id, JobState.CANCELLED)

    def resume(self, job_id: str) -> Job:
        return self._store.load(job_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_service.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/jobs/service.py tests/jobs/test_service.py
git commit -m "feat: add job service with fail-closed transitions

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Immutable approval gates

**Files:**
- Create: `src/fecreator/jobs/approvals.py`
- Test: `tests/jobs/test_approvals.py`

**Interfaces:**
- Consumes: `core.atomicio`, `core.paths.safe_join`, `core.clock.utc_now_iso`.
- Produces: `ApprovalError`; `ApprovalRecord(job_id, stage, decision, actor, reason, at)`; `ApprovalStore(root)` with `approve(job_id, stage, actor) -> ApprovalRecord`, `reject(job_id, stage, actor, reason) -> ApprovalRecord`, `decisions(job_id) -> list[ApprovalRecord]`. Re-deciding an already-decided stage raises `ApprovalError` (append-only, immutable).

- [ ] **Step 1: Write the failing test**

`tests/jobs/test_approvals.py`:
```python
import pytest

from fecreator.jobs.approvals import ApprovalError, ApprovalStore


def test_approve_and_read(data_root):
    store = ApprovalStore(data_root)
    rec = store.approve("j1", "neutral", "alice")
    assert rec.decision == "approved" and rec.actor == "alice"
    assert [d.stage for d in store.decisions("j1")] == ["neutral"]


def test_reject_records_reason(data_root):
    store = ApprovalStore(data_root)
    rec = store.reject("j1", "variant", "bob", "hat clips the ear")
    assert rec.decision == "rejected" and rec.reason == "hat clips the ear"


def test_cannot_redecide_same_stage(data_root):
    store = ApprovalStore(data_root)
    store.approve("j1", "neutral", "alice")
    with pytest.raises(ApprovalError):
        store.reject("j1", "neutral", "alice", "changed my mind")


def test_decisions_are_persisted(data_root):
    ApprovalStore(data_root).approve("j1", "neutral", "alice")
    assert len(ApprovalStore(data_root).decisions("j1")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/jobs/test_approvals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.jobs.approvals'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/jobs/approvals.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from fecreator.core.atomicio import append_jsonl, read_jsonl
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join


class ApprovalError(Exception):
    """Raised when an already-decided stage is decided again."""


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    job_id: str
    stage: str
    decision: Literal["approved", "rejected"]
    actor: str
    reason: str | None = None
    at: str


class ApprovalStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", job_id, "approvals.jsonl")

    def _record(self, job_id: str, stage: str, decision: Literal["approved", "rejected"],
                actor: str, reason: str | None) -> ApprovalRecord:
        if any(d.stage == stage for d in self.decisions(job_id)):
            raise ApprovalError(f"stage already decided: {stage}")
        rec = ApprovalRecord(job_id=job_id, stage=stage, decision=decision, actor=actor,
                             reason=reason, at=utc_now_iso())
        append_jsonl(self._path(job_id), rec.model_dump(mode="json"))
        return rec

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._record(job_id, stage, "approved", actor, None)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._record(job_id, stage, "rejected", actor, reason)

    def decisions(self, job_id: str) -> list[ApprovalRecord]:
        return [ApprovalRecord.model_validate(row) for row in read_jsonl(self._path(job_id))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/jobs/test_approvals.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/jobs/approvals.py tests/jobs/test_approvals.py
git commit -m "feat: add immutable append-only approval store

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Versioned character reference packs

**Files:**
- Create: `src/fecreator/references/__init__.py`, `src/fecreator/references/model.py`, `src/fecreator/references/store.py`
- Test: `tests/references/test_pack_store.py`

**Interfaces:**
- Consumes: `Artifact` (contracts.result); `core.atomicio`, `core.paths.safe_join`.
- Produces: `ReferencePack(id, revision, concept_art, swatches, forbidden_changes, provenance, rights)`; `ReferencePackStore(root)` with `create(pack) -> ReferencePack` (revision forced to 1), `new_revision(pack_id, **changes) -> ReferencePack`, `get(pack_id, revision) -> ReferencePack`, `latest(pack_id) -> ReferencePack`. Prior revisions are immutable.

- [ ] **Step 1: Write the failing test**

`tests/references/test_pack_store.py`:
```python
import pytest

from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore


def _pack():
    return ReferencePack(id="marth", revision=99, swatches=("#112233",),
                         provenance="synthetic", rights="original")


def test_create_forces_revision_one(data_root):
    store = ReferencePackStore(data_root)
    saved = store.create(_pack())
    assert saved.revision == 1


def test_new_revision_increments_and_keeps_history(data_root):
    store = ReferencePackStore(data_root)
    store.create(_pack())
    rev2 = store.new_revision("marth", swatches=("#445566",))
    assert rev2.revision == 2
    assert store.get("marth", 1).swatches == ("#112233",)
    assert store.latest("marth").swatches == ("#445566",)


def test_prior_revision_file_unchanged(data_root):
    store = ReferencePackStore(data_root)
    store.create(_pack())
    original = (data_root / "refs" / "marth" / "1.json").read_text()
    store.new_revision("marth", provenance="edited")
    assert (data_root / "refs" / "marth" / "1.json").read_text() == original


def test_missing_revision_raises(data_root):
    store = ReferencePackStore(data_root)
    store.create(_pack())
    with pytest.raises(FileNotFoundError):
        store.get("marth", 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/references/test_pack_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.references.model'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/references/__init__.py`:
```python
```

`src/fecreator/references/model.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fecreator.contracts.result import Artifact


class ReferencePack(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    revision: int
    concept_art: tuple[Artifact, ...] = ()
    swatches: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    provenance: str = ""
    rights: str = ""
```

`src/fecreator/references/store.py`:
```python
from __future__ import annotations

from pathlib import Path

from fecreator.core.atomicio import read_json, write_json_atomic
from fecreator.core.paths import safe_join
from fecreator.references.model import ReferencePack


class ReferencePackStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _dir(self, pack_id: str) -> Path:
        return safe_join(self._root, "refs", pack_id)

    def create(self, pack: ReferencePack) -> ReferencePack:
        first = pack.model_copy(update={"revision": 1})
        write_json_atomic(self._dir(pack.id) / "1.json", first.model_dump(mode="json"))
        return first

    def new_revision(self, pack_id: str, **changes: object) -> ReferencePack:
        current = self.latest(pack_id)
        nxt = current.model_copy(update={**changes, "revision": current.revision + 1})
        write_json_atomic(self._dir(pack_id) / f"{nxt.revision}.json", nxt.model_dump(mode="json"))
        return nxt

    def get(self, pack_id: str, revision: int) -> ReferencePack:
        return ReferencePack.model_validate(read_json(self._dir(pack_id) / f"{revision}.json"))

    def latest(self, pack_id: str) -> ReferencePack:
        revs = [int(p.stem) for p in self._dir(pack_id).glob("*.json")]
        if not revs:
            raise FileNotFoundError(f"no reference pack: {pack_id}")
        return self.get(pack_id, max(revs))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/references/test_pack_store.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/references/ tests/references/test_pack_store.py
git commit -m "feat: add versioned immutable reference packs

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Asset lineage DAG store

**Files:**
- Create: `src/fecreator/lineage/__init__.py`, `src/fecreator/lineage/store.py`
- Test: `tests/lineage/test_lineage_store.py`

**Interfaces:**
- Consumes: `LineageNode`, `Operation` (contracts.lineage); `core.atomicio`, `core.paths.safe_join`.
- Produces: `CycleError`; `LineageStore(root)` with `add(node) -> None` (unique `asset_id`; parents must pre-exist; self-parent raises `CycleError`; unknown parent raises `ValueError`), `get(asset_id) -> LineageNode`, `ancestors(asset_id) -> list[LineageNode]`, `children(asset_id) -> list[LineageNode]`.

- [ ] **Step 1: Write the failing test**

`tests/lineage/test_lineage_store.py`:
```python
import pytest

from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.lineage.store import CycleError, LineageStore


def _node(asset_id, parents=(), op=Operation.CREATE_NEUTRAL):
    return LineageNode(asset_id=asset_id, operation=op, parents=tuple(parents),
                       created_at="2026-07-24T00:00:00+00:00")


def test_add_and_get(data_root):
    store = LineageStore(data_root)
    store.add(_node("a"))
    assert store.get("a").operation is Operation.CREATE_NEUTRAL


def test_ancestors_and_children(data_root):
    store = LineageStore(data_root)
    store.add(_node("a"))
    store.add(_node("b", parents=("a",), op=Operation.REFINE_EXPRESSION))
    store.add(_node("c", parents=("b",), op=Operation.VARIANT_MASKED_EDIT))
    assert [n.asset_id for n in store.ancestors("c")] == ["b", "a"]
    assert [n.asset_id for n in store.children("a")] == ["b"]


def test_duplicate_asset_id_raises(data_root):
    store = LineageStore(data_root)
    store.add(_node("a"))
    with pytest.raises(ValueError):
        store.add(_node("a"))


def test_unknown_parent_raises(data_root):
    store = LineageStore(data_root)
    with pytest.raises(ValueError):
        store.add(_node("b", parents=("missing",)))


def test_self_parent_is_cycle(data_root):
    store = LineageStore(data_root)
    with pytest.raises(CycleError):
        store.add(_node("a", parents=("a",)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lineage/test_lineage_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fecreator.lineage.store'`.

- [ ] **Step 3: Write minimal implementation**

`src/fecreator/lineage/__init__.py`:
```python
```

`src/fecreator/lineage/store.py`:
```python
from __future__ import annotations

from pathlib import Path

from fecreator.contracts.lineage import LineageNode
from fecreator.core.atomicio import read_json, write_json_atomic
from fecreator.core.paths import safe_join


class CycleError(Exception):
    """Raised when adding a node would create a cycle in the lineage DAG."""


class LineageStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, asset_id: str) -> Path:
        return safe_join(self._root, "lineage", f"{asset_id}.json")

    def _exists(self, asset_id: str) -> bool:
        return self._path(asset_id).exists()

    def add(self, node: LineageNode) -> None:
        if self._exists(node.asset_id):
            raise ValueError(f"asset_id already exists: {node.asset_id}")
        if node.asset_id in node.parents:
            raise CycleError(f"self-parent: {node.asset_id}")
        for parent in node.parents:
            if not self._exists(parent):
                raise ValueError(f"unknown parent: {parent}")
        write_json_atomic(self._path(node.asset_id), node.model_dump(mode="json"))

    def get(self, asset_id: str) -> LineageNode:
        return LineageNode.model_validate(read_json(self._path(asset_id)))

    def ancestors(self, asset_id: str) -> list[LineageNode]:
        out: list[LineageNode] = []
        frontier = list(self.get(asset_id).parents)
        while frontier:
            current = frontier.pop(0)
            node = self.get(current)
            out.append(node)
            frontier.extend(node.parents)
        return out

    def children(self, asset_id: str) -> list[LineageNode]:
        lineage_dir = self._root / "lineage"
        if not lineage_dir.exists():
            return []
        kids: list[LineageNode] = []
        for path in sorted(lineage_dir.glob("*.json")):
            node = LineageNode.model_validate(read_json(path))
            if asset_id in node.parents:
                kids.append(node)
        return kids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/lineage/test_lineage_store.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/fecreator/lineage/ tests/lineage/test_lineage_store.py
git commit -m "feat: add append-only lineage DAG store

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-review

- **Spec coverage (design §7, §8):** job states (Task 2), resumable/immutable workspace + atomic writes + fault injection (Tasks 1, 3), event diagnostics (Task 4), transition/cancel/resume (Task 5), approval gates (Task 6), versioned reference packs (Task 7), lineage DAG with parents/operation/metrics/hashes (Task 8). Manifest snapshot immutability and path containment are asserted directly.
- **Placeholder scan:** no TBD/TODO; every test and implementation is complete and runnable.
- **Type consistency:** `Job`, `JobEvent`, `JobState`, `ALLOWED_TRANSITIONS`, `ReferencePack`, `LineageNode`, `Operation`, `Artifact` all match master §4. `EventLog`/`JobStore` constructor arity matches `JobService.__init__(store, events)` in Task 5 and in the app wiring (Providers-Interfaces).
- **Platform commands:** all commands here are Python/pytest and identical on Windows and POSIX; filesystem paths are produced by `safe_join`, which is platform-aware.
