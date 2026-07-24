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
        try:
            self._events.append(job.id, "created", "job created")
        except Exception:
            self._store.remove(job.id)
            raise
        return job

    def transition(self, job_id: str, to: JobState) -> Job:
        with self._store.locked(job_id):
            job = self._store.load(job_id)
            if to not in ALLOWED_TRANSITIONS[job.state]:
                raise InvalidTransitionError(f"{job.state} -> {to} is not allowed")

            previous = job.model_copy(deep=True)
            expected_revision = job.revision
            from_state = job.state
            job.state = to
            self._store._save_locked(job, expected_revision=expected_revision)
            try:
                self._events.append(
                    job.id,
                    "transition",
                    f"{from_state}->{to}",
                    {"from": from_state.value, "to": to.value},
                )
            except Exception:
                self._store._replace_locked(previous)
                raise
            return job

    def cancel(self, job_id: str) -> Job:
        return self.transition(job_id, JobState.CANCELLED)

    def resume(self, job_id: str) -> Job:
        return self._store.load(job_id)
