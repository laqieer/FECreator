from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fecreator.contracts.manifest import Manifest
from fecreator.core.atomicio import read_json, write_json_atomic
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import Job, JobState


class JobStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _job_dir(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", job_id)

    def _job_payload(self, job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "state": job.state,
            "revision": job.revision,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

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
        write_json_atomic(job_dir / "manifest.json", manifest.model_dump(mode="json"))
        write_json_atomic(job_dir / "job.json", self._job_payload(job))
        return job

    def load(self, job_id: str) -> Job:
        job_dir = self._job_dir(job_id)
        payload = read_json(job_dir / "job.json")
        manifest_payload = read_json(job_dir / "manifest.json")
        if not isinstance(payload, dict):
            raise TypeError("job.json must contain an object")
        return Job(
            id=str(payload["id"]),
            state=JobState(str(payload["state"])),
            manifest=Manifest.model_validate(manifest_payload),
            revision=int(payload["revision"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )

    def save(self, job: Job) -> None:
        job.updated_at = utc_now_iso()
        write_json_atomic(self._job_dir(job.id) / "job.json", self._job_payload(job))

    def list_jobs(self) -> list[str]:
        jobs_dir = self._root / "jobs"
        if not jobs_dir.exists():
            return []
        return sorted(entry.name for entry in jobs_dir.iterdir() if entry.is_dir())
