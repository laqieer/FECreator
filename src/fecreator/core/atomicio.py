from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _dump_json(obj: object, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(obj, sort_keys=True, indent=2) + "\n"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def write_json_atomic(path: Path, obj: object) -> None:
    _write_text_atomic(path, _dump_json(obj, pretty=True))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, obj: object) -> None:
    records = read_jsonl(path)
    records.append(obj)
    payload = "".join(f"{_dump_json(record, pretty=False)}\n" for record in records)
    _write_text_atomic(path, payload)


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
