from __future__ import annotations

from pathlib import Path

from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import _path_lock, _read_json_unlocked, _write_json_atomic_unlocked
from fecreator.core.paths import safe_join
from fecreator.jobs.model import ensure_non_empty_text


class CandidateCorruptionError(Exception):
    """Raised when a visible candidate snapshot is missing required data or malformed."""


class CandidateStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _normalize_job_id(self, job_id: str) -> str:
        return ensure_non_empty_text(job_id, field_name="job_id")

    def _job_dir(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", self._normalize_job_id(job_id))

    def _path(self, job_id: str) -> Path:
        return safe_join(self._job_dir(job_id), "candidate", "candidate.json")

    def _lock_path(self, job_id: str) -> Path:
        return safe_join(self._root, "jobs", ".locks", f"{self._normalize_job_id(job_id)}.lock")

    def _read_locked(self, job_id: str) -> CandidateSnapshot:
        path = self._path(job_id)
        try:
            payload = _read_json_unlocked(path)
            snapshot = CandidateSnapshot.model_validate(payload)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise CandidateCorruptionError(f"corrupt candidate snapshot: {path}") from exc
        if snapshot.job_id != self._normalize_job_id(job_id):
            raise CandidateCorruptionError(f"corrupt candidate snapshot: {path}")
        return snapshot

    def create(self, snapshot: CandidateSnapshot) -> CandidateSnapshot:
        normalized_job_id = self._normalize_job_id(snapshot.job_id)
        normalized_snapshot = snapshot.model_copy(update={"job_id": normalized_job_id})
        with _path_lock(
            self._job_dir(normalized_job_id),
            lock_path=self._lock_path(normalized_job_id),
        ):
            if self._path(normalized_job_id).exists():
                self._read_locked(normalized_job_id)
                raise FileExistsError(
                    f"candidate snapshot already exists for job {normalized_job_id}"
                )
            _write_json_atomic_unlocked(
                self._path(normalized_job_id),
                normalized_snapshot.model_dump(mode="json"),
            )
        return normalized_snapshot

    def load(self, job_id: str) -> CandidateSnapshot:
        normalized_job_id = self._normalize_job_id(job_id)
        with _path_lock(
            self._job_dir(normalized_job_id),
            lock_path=self._lock_path(normalized_job_id),
        ):
            return self._read_locked(normalized_job_id)
