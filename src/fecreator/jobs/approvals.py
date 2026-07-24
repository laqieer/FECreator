from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from fecreator.core.atomicio import _update_jsonl_atomic, read_jsonl
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join


class ApprovalError(Exception):
    """Raised when a stage receives more than one decision."""


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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

    def _record(
        self,
        job_id: str,
        stage: str,
        decision: Literal["approved", "rejected"],
        actor: str,
        reason: str | None,
    ) -> ApprovalRecord:
        def add_decision(records: list[object]) -> ApprovalRecord:
            existing = [ApprovalRecord.model_validate(row) for row in records]
            if any(record.stage == stage for record in existing):
                raise ApprovalError(f"stage already decided: {stage}")

            record = ApprovalRecord(
                job_id=job_id,
                stage=stage,
                decision=decision,
                actor=actor,
                reason=reason,
                at=utc_now_iso(),
            )
            records.append(record.model_dump(mode="json"))
            return record

        return _update_jsonl_atomic(self._path(job_id), add_decision)

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._record(job_id, stage, "approved", actor, None)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._record(job_id, stage, "rejected", actor, reason)

    def decisions(self, job_id: str) -> list[ApprovalRecord]:
        return [ApprovalRecord.model_validate(row) for row in read_jsonl(self._path(job_id))]
