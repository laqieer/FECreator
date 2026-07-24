from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, TypeVar

if os.name == "nt":
    import msvcrt

    def _lock_file(fh: BinaryIO) -> None:
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock_file(fh: BinaryIO) -> None:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:  # pragma: no cover
    import fcntl as posix_fcntl

    def _lock_file(fh: BinaryIO) -> None:
        posix_fcntl.flock(fh.fileno(), posix_fcntl.LOCK_EX)  # type: ignore[attr-defined]

    def _unlock_file(fh: BinaryIO) -> None:
        posix_fcntl.flock(fh.fileno(), posix_fcntl.LOCK_UN)  # type: ignore[attr-defined]


T = TypeVar("T")


def _dump_json(obj: object, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(obj, sort_keys=True, indent=2) + "\n"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


@contextmanager
def _path_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        fh.seek(0)
        _lock_file(fh)
        try:
            yield
        finally:
            fh.seek(0)
            _unlock_file(fh)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _write_jsonl_records(path: Path, records: list[Any]) -> None:
    payload = "".join(f"{_dump_json(record, pretty=False)}\n" for record in records)
    _write_text_atomic(path, payload)


def _update_jsonl_atomic(path: Path, updater: Callable[[list[Any]], T]) -> T:
    with _path_lock(path):
        records = read_jsonl(path)
        result = updater(records)
        _write_jsonl_records(path, records)
        return result


def write_json_atomic(path: Path, obj: object) -> None:
    _write_text_atomic(path, _dump_json(obj, pretty=True))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, obj: object) -> None:
    def add_record(records: list[Any]) -> None:
        records.append(obj)
        return None

    _update_jsonl_atomic(path, add_record)


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
