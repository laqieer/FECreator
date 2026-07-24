from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from fecreator.core.atomicio import append_jsonl, read_jsonl
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
        if any(existing.stage == stage for existing in self.decisions(job_id)):
            raise ApprovalError(f"stage already decided: {stage}")

        record = ApprovalRecord(
            job_id=job_id,
            stage=stage,
            decision=decision,
            actor=actor,
            reason=reason,
            at=utc_now_iso(),
        )
        append_jsonl(self._path(job_id), record.model_dump(mode="json"))
        return record

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._record(job_id, stage, "approved", actor, None)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._record(job_id, stage, "rejected", actor, reason)

    def decisions(self, job_id: str) -> list[ApprovalRecord]:
        return [ApprovalRecord.model_validate(row) for row in read_jsonl(self._path(job_id))]
