from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.contracts.review import CandidateSnapshot

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "manifest": Manifest,
    "result": JobResult,
    "candidate": CandidateSnapshot,
    "diagnostics": Diagnostic,
    "lineage": LineageNode,
    "capabilities": CapabilitySet,
}


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in SCHEMA_MODELS.items():
        output = out_dir / f"{name}.schema.json"
        schema_json = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        output.write_text(schema_json, encoding="utf-8", newline="\n")
        written.append(output)
    return written
