from __future__ import annotations

from fecreator.core.atomicio import append_jsonl, read_json, read_jsonl, write_json_atomic


def test_write_then_read(tmp_path) -> None:
    p = tmp_path / "a" / "x.json"

    write_json_atomic(p, {"k": 1})

    assert read_json(p) == {"k": 1}


def test_no_tmp_left_and_overwrites_stale_tmp(tmp_path) -> None:
    p = tmp_path / "x.json"
    (tmp_path / "x.json.tmp").write_text("garbage", encoding="utf-8")

    write_json_atomic(p, {"k": 2})

    assert read_json(p) == {"k": 2}
    assert not (tmp_path / "x.json.tmp").exists()


def test_append_jsonl(tmp_path) -> None:
    p = tmp_path / "log.jsonl"

    append_jsonl(p, {"n": 1})
    append_jsonl(p, {"n": 2})

    assert read_jsonl(p) == [{"n": 1}, {"n": 2}]


def test_read_jsonl_missing_is_empty(tmp_path) -> None:
    assert read_jsonl(tmp_path / "none.jsonl") == []
