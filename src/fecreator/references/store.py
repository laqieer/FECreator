from __future__ import annotations

import os
import shutil
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from fecreator.core.atomicio import (
    LockTimeoutError,
    _fsync_directory,
    _path_lock,
    _read_json_unlocked,
    _write_json_atomic_unlocked,
)
from fecreator.core.paths import ensure_storage_id_not_reserved, normalize_storage_id, safe_join
from fecreator.references.model import ReferencePack

STALE_STAGING_MAX_AGE_SECONDS = 300.0
STAGING_PREFIX = ".tmp-"
STAGING_LOCK_PREFIX = "staging-"


class ReferencePackCorruptionError(Exception):
    """Raised when a visible reference pack revision is missing or corrupt."""


class UnpinnedReferencePackError(ValueError):
    """Raised when a persisted job cannot replay an exact reference revision."""


class ReferencePackStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._cleanup_stale_staging_dirs()

    def _refs_dir(self) -> Path:
        return safe_join(self._root, "refs")

    def _locks_dir(self) -> Path:
        return safe_join(self._root, "refs", ".locks")

    def _normalize_pack_id(self, pack_id: str) -> str:
        normalized = normalize_storage_id(pack_id, field_name="pack_id")
        ensure_storage_id_not_reserved(
            normalized,
            field_name="pack_id",
            reserved_prefixes=(STAGING_LOCK_PREFIX,),
        )
        safe_join(self._refs_dir(), normalized)
        return normalized

    def _validate_revision(self, revision: int) -> int:
        if revision < 1:
            raise ValueError("revision must be >= 1")
        return revision

    def _pack_dir(self, pack_id: str) -> Path:
        return safe_join(self._root, "refs", self._normalize_pack_id(pack_id))

    def _revision_path(self, pack_id: str, revision: int) -> Path:
        return self._pack_dir(pack_id) / f"{self._validate_revision(revision)}.json"

    def _lock_target(self, pack_id: str) -> Path:
        return safe_join(self._root, "refs", ".locks", self._normalize_pack_id(pack_id))

    def _lock_path(self, pack_id: str) -> Path:
        return self._lock_target(pack_id).with_suffix(".lock")

    def _staging_dir(self, pack_id: str) -> Path:
        return safe_join(self._root, "refs", f"{STAGING_PREFIX}{self._normalize_pack_id(pack_id)}")

    def _staging_lock_target(self, pack_id: str) -> Path:
        return self._locks_dir() / f"staging-{self._normalize_pack_id(pack_id)}"

    def _staging_lock_target_from_dir(self, staging_dir: Path) -> Path:
        return self._locks_dir() / f"staging-{staging_dir.name.removeprefix(STAGING_PREFIX)}"

    def _staging_lock_file(self, staging_dir: Path) -> Path:
        target = self._staging_lock_target_from_dir(staging_dir)
        return target.with_suffix(target.suffix + ".lock")

    def _touch_staging_dir(self, staging_dir: Path) -> None:
        os.utime(staging_dir, None)

    def _cleanup_stale_staging_dirs(self) -> None:
        refs_dir = self._refs_dir()
        if not refs_dir.exists():
            return

        now = time.time()
        for entry in refs_dir.iterdir():
            if not entry.is_dir() or not entry.name.startswith(STAGING_PREFIX):
                continue
            age_seconds = now - entry.stat().st_mtime
            if age_seconds < STALE_STAGING_MAX_AGE_SECONDS:
                continue
            try:
                with (
                    _path_lock(
                        self._staging_lock_target_from_dir(entry),
                        timeout=0.01,
                        poll_interval=0.01,
                    ),
                    suppress(FileNotFoundError),
                ):
                    shutil.rmtree(entry)
            except LockTimeoutError:
                continue

    def _read_pack_payload_locked(self, path: Path) -> dict[str, Any]:
        payload = _read_json_unlocked(path)
        if not isinstance(payload, dict):
            raise TypeError("reference pack revision must contain an object")
        return payload

    def _read_pack_locked(self, pack_id: str, revision: int) -> ReferencePack:
        path = self._revision_path(pack_id, revision)
        try:
            payload = self._read_pack_payload_locked(path)
            pack = ReferencePack.model_validate(payload)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ReferencePackCorruptionError(f"corrupt reference pack revision: {path}") from exc
        if pack.id != self._normalize_pack_id(pack_id) or pack.revision != revision:
            raise ReferencePackCorruptionError(f"corrupt reference pack revision: {path}")
        return pack

    def _revision_numbers_locked(self, pack_id: str) -> list[int]:
        pack_dir = self._pack_dir(pack_id)
        if not pack_dir.exists():
            raise FileNotFoundError(pack_dir)

        revisions: list[int] = []
        for entry in pack_dir.iterdir():
            if entry.name.startswith(".") or entry.name.endswith(".tmp"):
                continue
            if entry.is_dir():
                raise ReferencePackCorruptionError(
                    f"unexpected directory in reference pack: {entry}"
                )
            if entry.suffix != ".json" or not entry.stem.isdecimal():
                raise ReferencePackCorruptionError(f"unexpected file in reference pack: {entry}")
            revisions.append(int(entry.stem))
        revisions.sort()

        if not revisions:
            raise ReferencePackCorruptionError(
                f"reference pack has no visible revisions: {pack_id}"
            )

        expected = list(range(1, max(revisions) + 1))
        if revisions != expected:
            raise ReferencePackCorruptionError(
                "reference pack "
                f"{pack_id} has missing revision(s): expected {expected}, found {revisions}"
            )
        return revisions

    def _latest_locked(self, pack_id: str) -> ReferencePack:
        revisions = self._revision_numbers_locked(pack_id)
        return self._read_pack_locked(pack_id, revisions[-1])

    def _validate_pack_for_write(self, pack: ReferencePack) -> None:
        """New writes require explicit provenance/rights.

        The store only persists caller-provided artifact and hash metadata; upstream
        ingestion owns immutable copying and hash calculation. Free-text fields such
        as source/provenance/rights are validated for non-empty values only.
        """

        if not pack.provenance.strip():
            raise ValueError("provenance must be non-empty for new reference pack revisions")
        if not pack.rights.strip():
            raise ValueError("rights must be non-empty for new reference pack revisions")

    def create(self, pack: ReferencePack) -> ReferencePack:
        self._cleanup_stale_staging_dirs()
        pack_id = self._normalize_pack_id(pack.id)
        first = ReferencePack.model_validate({**pack.model_dump(mode="python"), "revision": 1})
        self._validate_pack_for_write(first)
        refs_dir = self._refs_dir()
        refs_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = self._staging_dir(pack_id)
        final_dir = self._pack_dir(pack_id)
        replaced = False
        with _path_lock(final_dir, lock_path=self._lock_path(pack_id)):
            if final_dir.exists():
                self._revision_numbers_locked(pack_id)
                raise ValueError(f"reference pack already exists: {pack_id}")
            try:
                with _path_lock(self._staging_lock_target(pack_id)):
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    staging_dir.mkdir(parents=True, exist_ok=False)
                    self._touch_staging_dir(staging_dir)
                    _write_json_atomic_unlocked(
                        staging_dir / "1.json",
                        first.model_dump(mode="json"),
                    )
                    self._touch_staging_dir(staging_dir)
                    os.replace(staging_dir, final_dir)
                    replaced = True
                    _fsync_directory(refs_dir)
            except Exception:
                shutil.rmtree(final_dir if replaced else staging_dir, ignore_errors=True)
                raise
        return first

    def new_revision(self, pack_id: str, **changes: object) -> ReferencePack:
        if "id" in changes or "revision" in changes:
            raise ValueError("id and revision are immutable; use explicit new revisions")
        normalized = self._normalize_pack_id(pack_id)
        with _path_lock(self._pack_dir(normalized), lock_path=self._lock_path(normalized)):
            current = self._latest_locked(normalized)
            next_pack = ReferencePack.model_validate(
                {
                    **current.model_dump(mode="python"),
                    **changes,
                    "revision": current.revision + 1,
                }
            )
            self._validate_pack_for_write(next_pack)
            _write_json_atomic_unlocked(
                self._revision_path(normalized, next_pack.revision),
                next_pack.model_dump(mode="json"),
            )
            return next_pack

    def get(self, pack_id: str, revision: int) -> ReferencePack:
        normalized = self._normalize_pack_id(pack_id)
        with _path_lock(self._pack_dir(normalized), lock_path=self._lock_path(normalized)):
            return self._read_pack_locked(normalized, self._validate_revision(revision))

    def history(self, pack_id: str) -> list[ReferencePack]:
        normalized = self._normalize_pack_id(pack_id)
        with _path_lock(self._pack_dir(normalized), lock_path=self._lock_path(normalized)):
            return [
                self._read_pack_locked(normalized, revision)
                for revision in self._revision_numbers_locked(normalized)
            ]

    def latest(self, pack_id: str) -> ReferencePack:
        normalized = self._normalize_pack_id(pack_id)
        with _path_lock(self._pack_dir(normalized), lock_path=self._lock_path(normalized)):
            return self._latest_locked(normalized)
