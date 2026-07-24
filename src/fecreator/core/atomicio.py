from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _dump_json(obj: object, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(obj, sort_keys=True, indent=2) + "\n"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def write_json_atomic(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(_dump_json(obj, pretty=True), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(_dump_json(obj, pretty=False) + "\n")


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
