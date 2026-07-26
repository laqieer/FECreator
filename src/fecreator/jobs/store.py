from __future__ import annotations

import builtins
import os
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fecreator.contracts.manifest import Manifest
from fecreator.core.atomicio import (
    LockTimeoutError,
    _fsync_directory,
    _path_lock,
    _read_json_unlocked,
    _write_json_atomic_unlocked,
)
from fecreator.core.clock import utc_now_iso
from fecreator.core.paths import safe_join
from fecreator.jobs.model import Job, JobState, ensure_non_empty_text

STALE_STAGING_MAX_AGE_SECONDS = 300.0
STAGING_PREFIX = ".tmp-"


class JobCorruptionError(Exception):
    """Raised when a visible job directory is missing or contains corrupt state."""


class RevisionConflictError(Exception):
    """Raised when a caller attempts to save an outdated job revision."""


class JobStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._cleanup_stale_staging_dirs()

    def _jobs_dir(self) -> Path:
        return safe_join(self._root, "jobs")

    def _locks_dir(self) -> Path:
        return safe_join(self._root, "jobs", ".locks")

    def _normalize_job_id(self, job_id: str) -> str:
        return ensure_non_empty_text(job_id, field_name="job_id")

    def _job_dir(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", self._normalize_job_id(job_id))

    def _job_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def _manifest_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "manifest.json"

    def _lock_path(self, job_id: str) -> Path:
        normalized = self._normalize_job_id(job_id)
        return self._locks_dir() / f"{normalized}.lock"

    def _staging_dir(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", f"{STAGING_PREFIX}{self._normalize_job_id(job_id)}")

    def _staging_lock_target(self, job_id: str) -> Path:
        normalized = self._normalize_job_id(job_id)
        return self._locks_dir() / f"staging-{normalized}"

    def _staging_lock_target_from_dir(self, staging_dir: Path) -> Path:
        job_id = staging_dir.name.removeprefix(STAGING_PREFIX)
        return self._staging_lock_target(job_id)

    def _staging_lock_file(self, staging_dir: Path) -> Path:
        target = self._staging_lock_target_from_dir(staging_dir)
        return target.with_suffix(target.suffix + ".lock")

    def _touch_staging_dir(self, staging_dir: Path) -> None:
        os.utime(staging_dir, None)

    def _remove_staging_lock_file(self, staging_dir: Path) -> None:
        self._staging_lock_file(staging_dir).unlink(missing_ok=True)

    def _cleanup_stale_staging_dirs(self) -> None:
        jobs_dir = self._jobs_dir()
        if not jobs_dir.exists():
            return

        # Cleanup is intentionally conservative: only stage directories older than the
        # 300s contract are considered, and an active stage lock prevents deletion.
        # A process that stalls after mkdir but before locking could still race here,
        # but the long age threshold keeps that fail-closed window narrow in practice.
        now = time.time()
        for entry in jobs_dir.iterdir():
            if not entry.is_dir() or not entry.name.startswith(STAGING_PREFIX):
                continue
            age_seconds = now - entry.stat().st_mtime
            if age_seconds >= STALE_STAGING_MAX_AGE_SECONDS:
                try:
                    with _path_lock(
                        self._staging_lock_target_from_dir(entry),
                        timeout=0.01,
                        poll_interval=0.01,
                    ):
                        shutil.rmtree(entry, ignore_errors=True)
                except LockTimeoutError:
                    continue
                self._remove_staging_lock_file(entry)

    @contextmanager
    def locked(self, job_id: str) -> Iterator[None]:
        normalized = self._normalize_job_id(job_id)
        with _path_lock(self._job_path(normalized), lock_path=self._lock_path(normalized)):
            yield

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

    def _read_job_payload_locked(self, job_id: str) -> dict[str, Any]:
        payload = _read_json_unlocked(self._job_path(job_id))
        if not isinstance(payload, dict):
            raise TypeError("job.json must contain an object")
        return payload

    def _replace_locked(self, job: Job) -> None:
        _write_json_atomic_unlocked(self._job_path(job.id), self._job_payload(job))

    def _load_locked(self, job_id: str) -> Job:
        normalized = self._normalize_job_id(job_id)
        payload = self._read_job_payload_locked(normalized)
        manifest_payload = _read_json_unlocked(self._manifest_path(normalized))
        return Job(
            id=str(payload["id"]),
            state=JobState(str(payload["state"])),
            manifest=Manifest.model_validate(manifest_payload),
            revision=int(payload["revision"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )

    def create(self, manifest: Manifest) -> Job:
        self._cleanup_stale_staging_dirs()
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
        jobs_dir = self._jobs_dir()
        jobs_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = self._staging_dir(job_id)
        final_dir = self._job_dir(job_id)
        replaced = False
        try:
            with _path_lock(self._staging_lock_target(job_id)):
                staging_dir.mkdir(parents=True, exist_ok=True)
                self._touch_staging_dir(staging_dir)
                _write_json_atomic_unlocked(
                    staging_dir / "manifest.json",
                    manifest.model_dump(mode="json"),
                )
                self._touch_staging_dir(staging_dir)
                _write_json_atomic_unlocked(staging_dir / "job.json", self._job_payload(job))
                self._touch_staging_dir(staging_dir)
                os.replace(staging_dir, final_dir)
                replaced = True
                _fsync_directory(jobs_dir)
        except Exception:
            shutil.rmtree(final_dir if replaced else staging_dir, ignore_errors=True)
            raise
        finally:
            self._remove_staging_lock_file(staging_dir)
        return job

    def remove(self, job_id: str) -> None:
        shutil.rmtree(self._job_dir(job_id), ignore_errors=True)

    def load(self, job_id: str) -> Job:
        with self.locked(job_id):
            return self._load_locked(job_id)

    def _save_locked(
        self,
        job: Job,
        *,
        expected_revision: int,
        updated_at: str | None = None,
    ) -> None:
        payload = self._read_job_payload_locked(job.id)
        current_revision = int(payload["revision"])
        if current_revision != expected_revision or job.revision != expected_revision:
            raise RevisionConflictError(
                "expected revision "
                f"{expected_revision}, stored {current_revision}, in-memory {job.revision}"
            )

        next_revision = current_revision + 1
        persisted_updated_at = utc_now_iso() if updated_at is None else updated_at
        _write_json_atomic_unlocked(
            self._job_path(job.id),
            self._job_payload(job, revision=next_revision, updated_at=persisted_updated_at),
        )
        job.revision = next_revision
        job.updated_at = persisted_updated_at

    def save(self, job: Job, *, expected_revision: int) -> None:
        """Persist a job update using optimistic concurrency.

        Callers must pass the revision they loaded. Downstream Tasks 7+ should treat
        RevisionConflictError as a stale-write signal and reload before retrying.
        """

        with self.locked(job.id):
            self._save_locked(job, expected_revision=expected_revision)

    def list(self) -> builtins.list[Job]:
        self._cleanup_stale_staging_dirs()
        jobs_dir = self._jobs_dir()
        if not jobs_dir.exists():
            return []

        jobs: list[Job] = []
        for entry in sorted(jobs_dir.iterdir(), key=lambda path: path.name):
            if not entry.is_dir():
                continue
            if entry.name == ".locks" or entry.name.startswith(STAGING_PREFIX):
                continue
            if entry.name.startswith("."):
                raise JobCorruptionError(f"unexpected hidden directory in jobs store: {entry}")
            if not (entry / "job.json").exists() or not (entry / "manifest.json").exists():
                raise JobCorruptionError(f"job directory is missing required files: {entry}")
            try:
                with self.locked(entry.name):
                    job = self._load_locked(entry.name)
            except Exception as exc:  # pragma: no cover - exact error preserved by chaining
                raise JobCorruptionError(f"job directory is corrupt: {entry}") from exc
            jobs.append(job)
        return sorted(jobs, key=lambda job: job.id)

    def list_jobs(self) -> builtins.list[str]:
        return [job.id for job in self.list()]
