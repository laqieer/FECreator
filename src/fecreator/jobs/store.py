from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fecreator.contracts.manifest import Manifest
from fecreator.core.atomicio import read_json, write_json_atomic
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import Job, JobState


class RevisionConflictError(Exception):
    """Raised when a caller attempts to save an outdated job revision."""


class JobStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _job_dir(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", job_id)

    def _job_payload(
        self,
        job: Job,
        *,
        revision: int | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": job.id,
            "state": job.state.value,
            "revision": job.revision if revision is None else revision,
            "created_at": job.created_at,
            "updated_at": job.updated_at if updated_at is None else updated_at,
        }

    def _read_job_payload(self, job_id: str) -> dict[str, Any]:
        payload = read_json(self._job_dir(job_id) / "job.json")
        if not isinstance(payload, dict):
            raise TypeError("job.json must contain an object")
        return payload

    def create(self, manifest: Manifest) -> Job:
        job_id = uuid.uuid4().hex
        now = utc_now_iso()
        job = Job(
            id=job_id,
            state=JobState.CREATED,
            manifest=manifest,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            write_json_atomic(job_dir / "manifest.json", manifest.model_dump(mode="json"))
            write_json_atomic(job_dir / "job.json", self._job_payload(job))
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        return job

    def load(self, job_id: str) -> Job:
        payload = self._read_job_payload(job_id)
        manifest_payload = read_json(self._job_dir(job_id) / "manifest.json")
        return Job(
            id=str(payload["id"]),
            state=JobState(str(payload["state"])),
            manifest=Manifest.model_validate(manifest_payload),
            revision=int(payload["revision"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )

    def save(self, job: Job, *, expected_revision: int) -> None:
        payload = self._read_job_payload(job.id)
        current_revision = int(payload["revision"])
        if current_revision != expected_revision or job.revision != expected_revision:
            raise RevisionConflictError(
                "expected revision "
                f"{expected_revision}, stored {current_revision}, in-memory {job.revision}"
            )

        next_revision = current_revision + 1
        updated_at = utc_now_iso()
        write_json_atomic(
            self._job_dir(job.id) / "job.json",
            self._job_payload(job, revision=next_revision, updated_at=updated_at),
        )
        job.revision = next_revision
        job.updated_at = updated_at

    def list_jobs(self) -> list[str]:
        jobs_dir = self._root / "jobs"
        if not jobs_dir.exists():
            return []
        return sorted(entry.name for entry in jobs_dir.iterdir() if entry.is_dir())
