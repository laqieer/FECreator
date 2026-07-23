from __future__ import annotations

import json
from pathlib import Path

from fecreator.contracts.schemas import SCHEMA_MODELS, export_schemas

REPO_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def test_export_writes_all_models(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)

    assert {path.name for path in written} == {f"{name}.schema.json" for name in SCHEMA_MODELS}


def test_committed_schemas_are_up_to_date(tmp_path: Path) -> None:
    export_schemas(tmp_path)

    for name in SCHEMA_MODELS:
        fresh = json.loads((tmp_path / f"{name}.schema.json").read_text(encoding="utf-8"))
        committed = json.loads((REPO_SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert fresh == committed, f"{name}.schema.json is stale; regenerate"
