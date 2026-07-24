from __future__ import annotations

import errno
import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, TypeVar

if os.name == "nt":
    import msvcrt

    def _try_lock_file(fh: BinaryIO) -> None:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_file(fh: BinaryIO) -> None:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:  # pragma: no cover
    import fcntl as posix_fcntl

    def _try_lock_file(fh: BinaryIO) -> None:
        posix_fcntl.flock(  # type: ignore[attr-defined]
            fh.fileno(),
            posix_fcntl.LOCK_EX | posix_fcntl.LOCK_NB,  # type: ignore[attr-defined]
        )

    def _unlock_file(fh: BinaryIO) -> None:
        posix_fcntl.flock(fh.fileno(), posix_fcntl.LOCK_UN)  # type: ignore[attr-defined]


DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0
DEFAULT_LOCK_POLL_INTERVAL_SECONDS = 0.01
MAX_JSONL_RECORDS = 4_096
MAX_JSONL_BYTES = 4 * 1024 * 1024

T = TypeVar("T")


class LockTimeoutError(TimeoutError):
    """Raised when a sidecar lock cannot be acquired before the deadline."""


class JsonlBudgetError(ValueError):
    """Raised when a v1 JSONL log exceeds its bounded rewrite budget."""


"""v1 keeps atomic JSONL by rewriting the whole file under a lock.

This is intentionally bounded by MAX_JSONL_RECORDS and MAX_JSONL_BYTES so event and
approval logs remain finite until a true durable append strategy is introduced. When
the cap is reached, additional event-backed transitions fail loudly and must be
remediated by archiving or pruning prior history before retrying.
"""


def _dump_json(obj: object, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(obj, sort_keys=True, indent=2) + "\n"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _lock_sidecar_path(path: Path, lock_path: Path | None = None) -> Path:
    if lock_path is not None:
        return lock_path
    return path.with_suffix(path.suffix + ".lock")


def _is_lock_contention(error: OSError) -> bool:
    winerror = getattr(error, "winerror", None)
    if winerror in {32, 33, 36}:
        return True
    return error.errno in {errno.EACCES, errno.EAGAIN, errno.EPERM}


@contextmanager
def _path_lock(
    path: Path,
    *,
    lock_path: Path | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_LOCK_POLL_INTERVAL_SECONDS,
) -> Iterator[None]:
    if timeout <= 0:
        raise ValueError("timeout must be > 0")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be > 0")

    actual_lock_path = _lock_sidecar_path(path, lock_path)
    actual_lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with actual_lock_path.open("a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
            os.fsync(fh.fileno())
        fh.seek(0)
        while True:
            try:
                _try_lock_file(fh)
                break
            except OSError as exc:
                if not _is_lock_contention(exc):
                    raise
                if time.monotonic() >= deadline:
                    message = f"timed out acquiring lock for {path} via {actual_lock_path}"
                    raise LockTimeoutError(message) from exc
                time.sleep(poll_interval)
        try:
            yield
        finally:
            fh.seek(0)
            _unlock_file(fh)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _tmp_path_for(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".tmp")


def _write_tmp_file(tmp_path: Path, payload: bytes) -> None:
    with tmp_path.open("wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())


def _write_bytes_atomic_unlocked(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _tmp_path_for(path)
    try:
        _write_tmp_file(tmp_path, payload)
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _write_json_atomic_unlocked(path: Path, obj: object) -> None:
    _write_bytes_atomic_unlocked(path, _dump_json(obj, pretty=True).encode("utf-8"))


def write_json_atomic(path: Path, obj: object) -> None:
    with _path_lock(path):
        _write_json_atomic_unlocked(path, obj)


def _read_text_unlocked(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _read_json_unlocked(path: Path) -> Any:
    return json.loads(_read_text_unlocked(path))


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    with _path_lock(path):
        return _read_json_unlocked(path)


def _read_jsonl_unlocked(path: Path) -> list[Any]:
    if not path.exists():
        return []

    lines = _read_text_unlocked(path).splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []
    with _path_lock(path):
        return _read_jsonl_unlocked(path)


def _jsonl_payload(records: list[Any]) -> bytes:
    payload = "".join(f"{_dump_json(record, pretty=False)}\n" for record in records)
    return payload.encode("utf-8")


def _validate_jsonl_budget(records: list[Any], payload: bytes) -> None:
    if len(records) > MAX_JSONL_RECORDS:
        raise JsonlBudgetError(
            "v1 JSONL record budget exceeded; "
            f"current={len(records)} limit={MAX_JSONL_RECORDS}. "
            "archive or prune history before retrying event-backed operations."
        )
    if len(payload) > MAX_JSONL_BYTES:
        raise JsonlBudgetError(
            "v1 JSONL byte budget exceeded; "
            f"current={len(payload)} limit={MAX_JSONL_BYTES}. "
            "archive or prune history before retrying event-backed operations."
        )


def _write_jsonl_records_unlocked(path: Path, records: list[Any]) -> None:
    payload = _jsonl_payload(records)
    _validate_jsonl_budget(records, payload)
    _write_bytes_atomic_unlocked(path, payload)


def _update_jsonl_atomic(path: Path, updater: Callable[[list[Any]], T]) -> T:
    with _path_lock(path):
        records = _read_jsonl_unlocked(path)
        result = updater(records)
        _write_jsonl_records_unlocked(path, records)
        return result


def append_jsonl(path: Path, obj: object) -> None:
    def add_record(records: list[Any]) -> None:
        records.append(obj)
        return None

    _update_jsonl_atomic(path, add_record)
