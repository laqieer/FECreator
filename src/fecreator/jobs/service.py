from __future__ import annotations

from collections.abc import Callable, Sequence

from fecreator.contracts.manifest import Manifest
from fecreator.core.clock import utc_now_iso
from fecreator.jobs.events import EventLog, PendingEvent
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

    def create_job(
        self,
        manifest: Manifest,
        *,
        parent_candidate_id: str | None = None,
        extra_events: Sequence[PendingEvent] = (),
    ) -> Job:
        job = self._store.create(manifest, parent_candidate_id=parent_candidate_id)
        try:
            if extra_events:
                self._events.append_many(job.id, (("created", "job created", None), *extra_events))
            else:
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
        extra_events: Sequence[PendingEvent] = (),
    ) -> Job:
        return self.transition_path(
            job_id,
            (to,),
            before_persist=before_persist,
            rollback=rollback,
            extra_events=extra_events,
        )

    def transition_path(
        self,
        job_id: str,
        path: Sequence[JobState],
        *,
        before_persist: TransitionPublishHook | None = None,
        rollback: TransitionRollbackHook | None = None,
        extra_events: Sequence[PendingEvent] = (),
    ) -> Job:
        with self._store.locked(job_id):
            return self.transition_path_while_job_locked(
                job_id,
                path,
                before_persist=before_persist,
                rollback=rollback,
                extra_events=extra_events,
            )

    def resume_while_job_locked(self, job_id: str) -> Job:
        """Load a job while the caller owns its JobStore lock."""

        return self._store._load_locked(job_id)

    def transition_path_while_job_locked(
        self,
        job_id: str,
        path: Sequence[JobState],
        *,
        before_persist: TransitionPublishHook | None = None,
        rollback: TransitionRollbackHook | None = None,
        extra_events: Sequence[PendingEvent] = (),
    ) -> Job:
        """Transition a job while the caller owns its JobStore lock."""

        job = self._store._load_locked(job_id)
        previous = job.model_copy(deep=True)
        expected_revision = job.revision
        current_state = job.state
        transition_events: list[PendingEvent] = []
        for next_state in path:
            if next_state is current_state:
                continue
            if next_state not in ALLOWED_TRANSITIONS[current_state]:
                raise InvalidTransitionError(f"{current_state} -> {next_state} is not allowed")
            transition_events.append(
                (
                    "transition",
                    f"{current_state}->{next_state}",
                    {"from": current_state.value, "to": next_state.value},
                )
            )
            current_state = next_state

        if not transition_events:
            if path:
                raise InvalidTransitionError(f"{job.state} -> {job.state} is not allowed")
            return job

        persisted_updated_at = utc_now_iso()
        candidate = job.model_copy(deep=True)
        candidate.state = current_state
        candidate.revision = expected_revision + 1
        candidate.updated_at = persisted_updated_at
        persisted = False
        try:
            if before_persist is not None:
                before_persist(candidate)
            job.state = current_state
            self._store._save_locked(
                job,
                expected_revision=expected_revision,
                updated_at=persisted_updated_at,
            )
            persisted = True
            self._events.append_many(job.id, (*transition_events, *extra_events))
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

    def record_event(
        self,
        job_id: str,
        kind: str,
        message: str,
        data: dict[str, str | int | float | bool] | None = None,
        *,
        before_persist: TransitionPublishHook | None = None,
        rollback: TransitionRollbackHook | None = None,
    ) -> Job:
        with self._store.locked(job_id):
            job = self._store._load_locked(job_id)
            try:
                if before_persist is not None:
                    before_persist(job)
                self._events.append(job.id, kind, message, data)
            except Exception as exc:
                cleanup_error: Exception | None = None
                if rollback is not None and before_persist is not None:
                    try:
                        rollback()
                    except Exception as cleanup_exc:
                        cleanup_error = cleanup_exc
                if cleanup_error is not None:
                    raise cleanup_error from exc
                raise
            return job

    def cancel(self, job_id: str) -> Job:
        return self.transition(job_id, JobState.CANCELLED)

    def resume(self, job_id: str) -> Job:
        return self._store.load(job_id)
