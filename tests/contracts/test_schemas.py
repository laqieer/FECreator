from __future__ import annotations

import json
from pathlib import Path

import fecreator.contracts as contracts
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


def test_top_level_contracts_module_does_not_export_schema_helpers() -> None:
    assert not hasattr(contracts, "SCHEMA_MODELS")
    assert not hasattr(contracts, "export_schemas")


def test_mapping_field_schemas_remain_object_shaped(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    candidate_schema = json.loads((tmp_path / "candidate.schema.json").read_text(encoding="utf-8"))
    manifest_schema = json.loads((tmp_path / "manifest.schema.json").read_text(encoding="utf-8"))
    lineage_schema = json.loads((tmp_path / "lineage.schema.json").read_text(encoding="utf-8"))

    assert candidate_schema["properties"]["metrics"]["type"] == "object"
    assert manifest_schema["properties"]["params"]["type"] == "object"
    assert lineage_schema["properties"]["params"]["type"] == "object"
    assert lineage_schema["properties"]["metrics"]["type"] == "object"


def test_candidate_created_at_schema_uses_date_time_format(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    candidate_schema = json.loads((tmp_path / "candidate.schema.json").read_text(encoding="utf-8"))

    assert candidate_schema["properties"]["created_at"]["format"] == "date-time"


def test_lineage_created_at_schema_uses_date_time_format(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    lineage_schema = json.loads((tmp_path / "lineage.schema.json").read_text(encoding="utf-8"))

    assert lineage_schema["properties"]["created_at"]["format"] == "date-time"


def test_manifest_schema_includes_pinned_reference_revision(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    manifest_schema = json.loads((tmp_path / "manifest.schema.json").read_text(encoding="utf-8"))

    assert manifest_schema["properties"]["character_ref_pack_rev"]["anyOf"][0]["minimum"] == 1


def test_committed_schema_files_match_the_exported_inventory() -> None:
    committed = {path.name for path in REPO_SCHEMAS.glob("*.schema.json")}

    assert committed == {f"{name}.schema.json" for name in SCHEMA_MODELS}


def test_committed_manifest_schema_pins_the_frozen_v1_literals() -> None:
    manifest_schema = json.loads((REPO_SCHEMAS / "manifest.schema.json").read_text("utf-8"))
    properties = manifest_schema["properties"]

    assert properties["version"]["const"] == "1.0"
    assert properties["version"]["default"] == "1.0"
    assert properties["asset_type"]["const"] == "portrait"
    assert properties["target_spec"]["const"] == "fe-gba-portrait-standard"
    assert properties["workflow"]["enum"] == [
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    ]
    assert manifest_schema["additionalProperties"] is False


def test_committed_candidate_schema_pins_the_frozen_v1_version() -> None:
    candidate_schema = json.loads((REPO_SCHEMAS / "candidate.schema.json").read_text("utf-8"))

    assert candidate_schema["properties"]["version"]["const"] == "1.0"
    assert candidate_schema["additionalProperties"] is False
