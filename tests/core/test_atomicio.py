from __future__ import annotations

from pathlib import Path

import pytest

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


def test_read_jsonl_missing_is_empty(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "none.jsonl") == []
