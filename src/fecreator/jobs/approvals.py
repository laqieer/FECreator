from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from fecreator.core.atomicio import _update_jsonl_atomic, read_jsonl
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import ensure_aware_iso_timestamp, ensure_non_empty_text


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

    @field_validator("job_id", "stage", "actor", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "text"
        return ensure_non_empty_text(value, field_name=field_name)

    @field_validator("reason", mode="after")
    @classmethod
    def _validate_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_non_empty_text(value, field_name="reason")

    @field_validator("at", mode="after")
    @classmethod
    def _validate_at(cls, value: str) -> str:
        return ensure_aware_iso_timestamp(value, field_name="at")

    @model_validator(mode="after")
    def _validate_decision_reason(self) -> ApprovalRecord:
        if self.decision == "approved" and self.reason is not None:
            raise ValueError("approved records must not include a rejection reason")
        if self.decision == "rejected" and self.reason is None:
            raise ValueError("rejected records require a non-empty reason")
        return self


class ApprovalStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, job_id: str) -> Path:
        normalized = ensure_non_empty_text(job_id, field_name="job_id")
        return safe_join(self._root, "jobs", normalized, "approvals.jsonl")

    def _record(
        self,
        job_id: str,
        stage: str,
        decision: Literal["approved", "rejected"],
        actor: str,
        reason: str | None,
    ) -> ApprovalRecord:
        normalized_job_id = ensure_non_empty_text(job_id, field_name="job_id")
        normalized_stage = ensure_non_empty_text(stage, field_name="stage")
        normalized_actor = ensure_non_empty_text(actor, field_name="actor")
        normalized_reason = (
            ensure_non_empty_text(reason, field_name="reason") if reason is not None else None
        )

        def add_decision(records: list[object]) -> ApprovalRecord:
            existing = [ApprovalRecord.model_validate(row) for row in records]
            if any(record.stage == normalized_stage for record in existing):
                raise ApprovalError(f"stage already decided: {normalized_stage}")

            record = ApprovalRecord(
                job_id=normalized_job_id,
                stage=normalized_stage,
                decision=decision,
                actor=normalized_actor,
                reason=normalized_reason,
                at=utc_now_iso(),
            )
            records.append(record.model_dump(mode="json"))
            return record

        return _update_jsonl_atomic(self._path(normalized_job_id), add_decision)

    def approve(self, job_id: str, stage: str, actor: str) -> ApprovalRecord:
        return self._record(job_id, stage, "approved", actor, None)

    def reject(self, job_id: str, stage: str, actor: str, reason: str) -> ApprovalRecord:
        return self._record(job_id, stage, "rejected", actor, reason)

    def decisions(self, job_id: str) -> list[ApprovalRecord]:
        normalized_job_id = ensure_non_empty_text(job_id, field_name="job_id")
        rows = read_jsonl(self._path(normalized_job_id))
        return [ApprovalRecord.model_validate(row) for row in rows]
