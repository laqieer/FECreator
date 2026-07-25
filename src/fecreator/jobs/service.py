from __future__ import annotations

from collections.abc import Callable

from fecreator.contracts.manifest import Manifest
from fecreator.core.clock import utc_now_iso
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import ALLOWED_TRANSITIONS, Job, JobState
from fecreator.jobs.store import JobStore


class InvalidTransitionError(Exception):
    """Raised when a job state transition is not allowed."""


TransitionPublishHook = Callable[[Job], None]
TransitionRollbackHook = Callable[[], None]


class JobService:
    def __init__(self, store: JobStore, events: EventLog) -> None:
        self._store = store
        self._events = events

    def create_job(self, manifest: Manifest) -> Job:
        job = self._store.create(manifest)
        try:
            self._events.append(job.id, "created", "job created")
        except Exception:
            self._store.remove(job.id)
            raise
        return job

    def transition(
        self,
        job_id: str,
        to: JobState,
        *,
        before_persist: TransitionPublishHook | None = None,
        rollback: TransitionRollbackHook | None = None,
    ) -> Job:
        with self._store.locked(job_id):
            job = self._store._load_locked(job_id)
            if to not in ALLOWED_TRANSITIONS[job.state]:
                raise InvalidTransitionError(f"{job.state} -> {to} is not allowed")

            previous = job.model_copy(deep=True)
            expected_revision = job.revision
            from_state = job.state
            job.state = to
            persisted_updated_at = utc_now_iso()
            candidate = job.model_copy(deep=True)
            candidate.revision = expected_revision + 1
            candidate.updated_at = persisted_updated_at
            persisted = False
            try:
                if before_persist is not None:
                    before_persist(candidate)
                self._store._save_locked(
                    job,
                    expected_revision=expected_revision,
                    updated_at=persisted_updated_at,
                )
                persisted = True
                self._events.append(
                    job.id,
                    "transition",
                    f"{from_state}->{to}",
                    {"from": from_state.value, "to": to.value},
                )
            except Exception as exc:
                cleanup_error: Exception | None = None
                if rollback is not None and before_persist is not None:
                    try:
                        rollback()
                    except Exception as cleanup_exc:
                        cleanup_error = cleanup_exc
                if persisted:
                    self._store._replace_locked(previous)
                if cleanup_error is not None:
                    raise cleanup_error from exc
                raise
            return job

    def cancel(self, job_id: str) -> Job:
        return self.transition(job_id, JobState.CANCELLED)

    def resume(self, job_id: str) -> Job:
        return self._store.load(job_id)
