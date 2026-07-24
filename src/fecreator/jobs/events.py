from __future__ import annotations

from pathlib import Path

from fecreator.core.atomicio import _update_jsonl_atomic, read_jsonl
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import JobEvent, ensure_non_empty_text

EventData = dict[str, str | int | float | bool]


class EventLog:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, job_id: str) -> Path:
        normalized = ensure_non_empty_text(job_id, field_name="job_id")
        return safe_join(self._root, "jobs", normalized, "events.jsonl")

    def append(
        self,
        job_id: str,
        kind: str,
        message: str,
        data: EventData | None = None,
    ) -> JobEvent:
        normalized_job_id = ensure_non_empty_text(job_id, field_name="job_id")
        normalized_kind = ensure_non_empty_text(kind, field_name="kind")
        normalized_message = ensure_non_empty_text(message, field_name="message")

        def add_event(records: list[object]) -> JobEvent:
            event = JobEvent(
                seq=len(records),
                at=utc_now_iso(),
                kind=normalized_kind,
                message=normalized_message,
                data=data or {},
            )
            records.append(event.model_dump(mode="json"))
            return event

        return _update_jsonl_atomic(self._path(normalized_job_id), add_event)

    def read(self, job_id: str) -> list[JobEvent]:
        normalized_job_id = ensure_non_empty_text(job_id, field_name="job_id")
        return [JobEvent.model_validate(row) for row in read_jsonl(self._path(normalized_job_id))]
