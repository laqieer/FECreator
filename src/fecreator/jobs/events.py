from __future__ import annotations

from pathlib import Path

from fecreator.core.atomicio import _update_jsonl_atomic, read_jsonl
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import JobEvent

EventData = dict[str, str | int | float | bool]


class EventLog:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", job_id, "events.jsonl")

    def append(
        self,
        job_id: str,
        kind: str,
        message: str,
        data: EventData | None = None,
    ) -> JobEvent:
        def add_event(records: list[object]) -> JobEvent:
            event = JobEvent(
                seq=len(records),
                at=utc_now_iso(),
                kind=kind,
                message=message,
                data=data or {},
            )
            records.append(event.model_dump(mode="json"))
            return event

        return _update_jsonl_atomic(self._path(job_id), add_event)

    def read(self, job_id: str) -> list[JobEvent]:
        return [JobEvent.model_validate(row) for row in read_jsonl(self._path(job_id))]
