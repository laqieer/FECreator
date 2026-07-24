from __future__ import annotations

import threading
from pathlib import Path

import pytest

from fecreator.core import atomicio as atomicio_module
from fecreator.core.atomicio import append_jsonl, read_json, read_jsonl, write_json_atomic


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


def test_append_jsonl_failure_does_not_corrupt_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "log.jsonl"
    append_jsonl(p, {"n": 1})
    original = p.read_text(encoding="utf-8")
    tmp = p.with_suffix(p.suffix + ".tmp")
    original_write_text = Path.write_text

    def fake_write_text(self: Path, data: str, *args, **kwargs) -> int:
        if self == tmp:
            halfway = max(1, len(data) // 2)
            original_write_text(self, data[:halfway], *args, **kwargs)
            raise OSError("boom")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fake_write_text)

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
    original_read_jsonl = atomicio_module.read_jsonl
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

    monkeypatch.setattr(atomicio_module, "read_jsonl", fake_read_jsonl)

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
