from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from fecreator.core import atomicio as atomicio_module
from fecreator.core.atomicio import (
    LockTimeoutError,
    append_jsonl,
    read_json,
    read_jsonl,
    write_json_atomic,
)


def _worker_script(tmp_path: Path) -> Path:
    script = tmp_path / "atomicio_worker.py"
    script.write_text(
        """
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fecreator.core.atomicio import (
    LockTimeoutError,
    _path_lock,
    append_jsonl,
    read_json,
    write_json_atomic,
)


def main() -> int:
    command = sys.argv[1]
    path = Path(sys.argv[2])

    if command == "hold-lock":
        ready = Path(sys.argv[3])
        hold_seconds = float(sys.argv[4])
        with _path_lock(path, timeout=5.0, poll_interval=0.01):
            ready.write_text("ready", encoding="utf-8")
            time.sleep(hold_seconds)
        return 0

    if command == "append-jsonl":
        value = int(sys.argv[3])
        start = Path(sys.argv[4])
        while not start.exists():
            time.sleep(0.01)
        append_jsonl(path, {"n": value})
        return 0

    if command == "read-json-loop":
        start = Path(sys.argv[3])
        iterations = int(sys.argv[4])
        delay = float(sys.argv[5])
        while not start.exists():
            time.sleep(0.01)
        for _ in range(iterations):
            read_json(path)
            time.sleep(delay)
        return 0

    if command == "write-json-loop":
        start = Path(sys.argv[3])
        iterations = int(sys.argv[4])
        delay = float(sys.argv[5])
        while not start.exists():
            time.sleep(0.01)
        for value in range(iterations):
            write_json_atomic(path, {"n": value})
            time.sleep(delay)
        return 0

    if command == "timeout-lock":
        timeout_seconds = float(sys.argv[3])
        try:
            with _path_lock(path, timeout=timeout_seconds, poll_interval=0.01):
                return 0
        except LockTimeoutError:
            return 3

    raise RuntimeError(command)


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    return script


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_dir if not existing else f"{src_dir}{os.pathsep}{existing}"
    return env


def test_write_then_read(tmp_path: Path) -> None:
    p = tmp_path / "a" / "x.json"

    write_json_atomic(p, {"k": 1})

    assert read_json(p) == {"k": 1}


def test_no_tmp_left_and_overwrites_stale_tmp(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    (tmp_path / "x.json.tmp").write_text("garbage", encoding="utf-8")

    write_json_atomic(p, {"k": 2})

    assert read_json(p) == {"k": 2}
    assert not (tmp_path / "x.json.tmp").exists()


def test_append_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"

    append_jsonl(p, {"n": 1})
    append_jsonl(p, {"n": 2})

    assert read_jsonl(p) == [{"n": 1}, {"n": 2}]
    assert b"\r\n" not in p.read_bytes()


def test_append_jsonl_failure_does_not_corrupt_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "log.jsonl"
    append_jsonl(p, {"n": 1})
    original = p.read_text(encoding="utf-8")
    tmp = p.with_suffix(".jsonl.tmp")
    original_write_tmp_file = atomicio_module._write_tmp_file

    def fake_write_tmp_file(path: Path, payload: bytes) -> None:
        if path == tmp:
            halfway = max(1, len(payload) // 2)
            path.write_bytes(payload[:halfway])
            raise OSError("boom")
        original_write_tmp_file(path, payload)

    monkeypatch.setattr(atomicio_module, "_write_tmp_file", fake_write_tmp_file)

    with pytest.raises(OSError, match="boom"):
        append_jsonl(p, {"n": 2})

    assert p.read_text(encoding="utf-8") == original
    assert read_jsonl(p) == [{"n": 1}]


def test_append_jsonl_serializes_concurrent_writers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "log.jsonl"
    append_jsonl(p, {"n": 1})
    first_read_started = threading.Event()
    release_first_writer = threading.Event()
    original_read_jsonl = atomicio_module._read_jsonl_unlocked
    read_count = 0
    count_lock = threading.Lock()
    errors: list[Exception] = []

    def fake_read_jsonl(path: Path) -> list[object]:
        nonlocal read_count
        rows = original_read_jsonl(path)
        if path == p:
            with count_lock:
                read_count += 1
                current_read = read_count
            if current_read == 1:
                first_read_started.set()
                if not release_first_writer.wait(timeout=5):
                    raise TimeoutError("timed out waiting to release writer")
        return rows

    def worker(value: int) -> None:
        try:
            append_jsonl(p, {"n": value})
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            errors.append(exc)

    monkeypatch.setattr(atomicio_module, "_read_jsonl_unlocked", fake_read_jsonl)

    first = threading.Thread(target=worker, args=(2,))
    second = threading.Thread(target=worker, args=(3,))
    first.start()
    assert first_read_started.wait(timeout=5)
    second.start()
    release_first_writer.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert read_jsonl(p) == [{"n": 1}, {"n": 2}, {"n": 3}]


def test_read_jsonl_missing_is_empty(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "none.jsonl") == []


def test_write_json_atomic_preserves_lf_bytes(tmp_path: Path) -> None:
    p = tmp_path / "x.json"

    write_json_atomic(p, {"k": 1})

    assert b"\r\n" not in p.read_bytes()


def test_write_json_atomic_flushes_then_fsyncs_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "x.json"
    events: list[str] = []
    original_open = Path.open

    class Recorder(io.BytesIO):
        def __enter__(self) -> Recorder:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            self.close()
            return False

        def write(self, data: bytes) -> int:
            events.append("write")
            return super().write(data)

        def flush(self) -> None:
            events.append("flush")
            super().flush()

        def fileno(self) -> int:
            return 99

    def fake_open(self: Path, mode: str = "r", *args, **kwargs):
        if self == p.with_suffix(".json.tmp") and mode == "wb":
            events.append("open")
            return Recorder()
        return original_open(self, mode, *args, **kwargs)

    def fake_fsync(fd: int) -> None:
        events.append(f"fsync:{fd}")

    def fake_replace(source: Path, target: Path) -> None:
        events.append("replace")

    def fake_fsync_directory(path: Path) -> None:
        events.append(f"dirsync:{path.name}")

    @contextmanager
    def unlocked_path_lock(*args, **kwargs):
        yield

    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(atomicio_module.os, "fsync", fake_fsync)
    monkeypatch.setattr(atomicio_module.os, "replace", fake_replace)
    monkeypatch.setattr(atomicio_module, "_fsync_directory", fake_fsync_directory)
    monkeypatch.setattr(atomicio_module, "_path_lock", unlocked_path_lock)

    write_json_atomic(p, {"k": 1})

    assert events == [
        "open",
        "write",
        "flush",
        "fsync:99",
        "replace",
        "dirsync:" + p.parent.name,
    ]


def test_write_json_atomic_cleans_tmp_after_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "x.json"

    def fake_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(atomicio_module.os, "replace", fake_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_json_atomic(p, {"k": 1})

    assert not p.with_suffix(".json.tmp").exists()


def test_append_jsonl_enforces_v1_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "log.jsonl"
    monkeypatch.setattr(atomicio_module, "MAX_JSONL_RECORDS", 1)

    append_jsonl(p, {"n": 1})

    with pytest.raises(ValueError):
        append_jsonl(p, {"n": 2})


def test_repeated_operations_reuse_single_lock_file(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"

    append_jsonl(p, {"n": 1})
    append_jsonl(p, {"n": 2})
    read_jsonl(p)

    assert list(tmp_path.glob("*.lock")) == [p.with_suffix(".jsonl.lock")]


def test_cross_process_lock_timeout(tmp_path: Path) -> None:
    p = tmp_path / "shared.json"
    script = _worker_script(tmp_path)
    ready = tmp_path / "ready.txt"
    env = _worker_env()
    holder = subprocess.Popen(
        [sys.executable, str(script), "hold-lock", str(p), str(ready), "0.8"],
        env=env,
    )
    try:
        deadline = time.time() + 5
        while not ready.exists():
            assert time.time() < deadline
            time.sleep(0.01)

        with (
            pytest.raises(LockTimeoutError),
            atomicio_module._path_lock(
                p,
                timeout=0.1,
                poll_interval=0.01,
            ),
        ):
            pass
    finally:
        holder.wait(timeout=5)


def test_cross_process_multiple_writers_are_serialized(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    script = _worker_script(tmp_path)
    start = tmp_path / "start.txt"
    env = _worker_env()
    first = subprocess.Popen(
        [sys.executable, str(script), "append-jsonl", str(p), "2", str(start)],
        env=env,
    )
    second = subprocess.Popen(
        [sys.executable, str(script), "append-jsonl", str(p), "3", str(start)],
        env=env,
    )
    start.write_text("go", encoding="utf-8")

    assert first.wait(timeout=5) == 0
    assert second.wait(timeout=5) == 0
    assert read_jsonl(p) == [{"n": 2}, {"n": 3}] or read_jsonl(p) == [{"n": 3}, {"n": 2}]


def test_cross_process_reader_and_writer_coordinate_on_windows_safe_path(tmp_path: Path) -> None:
    p = tmp_path / "shared.json"
    write_json_atomic(p, {"n": 0})
    script = _worker_script(tmp_path)
    start = tmp_path / "start-reader-writer.txt"
    env = _worker_env()
    reader = subprocess.Popen(
        [sys.executable, str(script), "read-json-loop", str(p), str(start), "20", "0.01"],
        env=env,
    )
    writer = subprocess.Popen(
        [sys.executable, str(script), "write-json-loop", str(p), str(start), "8", "0.01"],
        env=env,
    )
    start.write_text("go", encoding="utf-8")

    assert reader.wait(timeout=10) == 0
    assert writer.wait(timeout=10) == 0
    assert "n" in read_json(p)
