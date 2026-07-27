"""Creating a job with a broken reference pack must fail structurally.

``create_job()`` pins the reference pack revision, so a missing or corrupt pack
is discovered *inside* the create call. Until this wave the failure escaped the
adapters untranslated: HTTP answered a bare 500 and the CLI printed a traceback
that quoted the absolute data root.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from fecreator.app import FeCreatorApp
from fecreator.contracts.result import Artifact
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import run
from fecreator.interfaces.http_api import create_api
from fecreator.interfaces.mcp_server import make_handlers
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore

_MISSING_PACK = "no-such-pack"
_CORRUPT_PACK = "corrupt-pack"


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _manifest_payload(pack_id: str | None, revision: int | None = None) -> dict[str, object]:
    return {
        "version": "1.0",
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": "fake",
        "character_ref_pack": pack_id,
        "character_ref_pack_rev": revision,
        "sources": [{"kind": "text", "ref": "hero"}],
        "edit": None,
        "params": {},
    }


def _corrupt_pack(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(
        ReferencePack(
            id=_CORRUPT_PACK,
            revision=1,
            source="synthetic fixture prompt",
            concept_art=(
                Artifact(
                    role="concept_art",
                    path="incoming/front.png",
                    sha256="a" * 64,
                    media_type="image/png",
                ),
            ),
            traits={"hair": "blue"},
            swatches=("#112233",),
            forbidden_changes=("change face shape",),
            provenance="synthetic-fixture",
            rights="original",
        )
    )
    (data_root / "refs" / _CORRUPT_PACK / "1.json").write_text("{", encoding="utf-8")


def _manifest_file(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _assert_no_absolute_root(payload: str, data_root: Path) -> None:
    root = str(data_root)
    assert root not in payload
    assert root.replace("\\", "/") not in payload
    assert root.replace("\\", "\\\\") not in payload


def test_http_create_job_maps_a_missing_reference_pack(data_root: Path) -> None:
    client = TestClient(create_api(_app(data_root)))

    response = client.post("/api/jobs", json=_manifest_payload(_MISSING_PACK))

    assert response.status_code == 404
    assert [diagnostic["code"] for diagnostic in response.json()] == ["UNKNOWN_REFERENCE_PACK"]
    assert response.json()[0]["where"] == _MISSING_PACK
    _assert_no_absolute_root(response.text, data_root)


def test_http_create_job_maps_a_corrupt_reference_pack(data_root: Path) -> None:
    _corrupt_pack(data_root)
    client = TestClient(create_api(_app(data_root)))

    response = client.post("/api/jobs", json=_manifest_payload(_CORRUPT_PACK))

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == ["CORRUPT_REFERENCE_PACK"]
    assert response.json()[0]["where"] == _CORRUPT_PACK
    _assert_no_absolute_root(response.text, data_root)


def test_http_create_job_maps_a_missing_pinned_revision(data_root: Path) -> None:
    _corrupt_pack(data_root)
    client = TestClient(create_api(_app(data_root)))

    response = client.post("/api/jobs", json=_manifest_payload(_CORRUPT_PACK, revision=7))

    assert response.status_code == 404
    assert [diagnostic["code"] for diagnostic in response.json()] == ["UNKNOWN_REFERENCE_PACK"]
    _assert_no_absolute_root(response.text, data_root)


def test_cli_create_job_maps_a_missing_reference_pack(data_root: Path, tmp_path: Path) -> None:
    out = io.StringIO()
    manifest = _manifest_file(tmp_path, _manifest_payload(_MISSING_PACK))

    rc = run(_app(data_root), ["job", "create", "--manifest", str(manifest)], out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == ["UNKNOWN_REFERENCE_PACK"]
    _assert_no_absolute_root(payload, data_root)


def test_cli_create_job_maps_a_corrupt_reference_pack(data_root: Path, tmp_path: Path) -> None:
    _corrupt_pack(data_root)
    out = io.StringIO()
    manifest = _manifest_file(tmp_path, _manifest_payload(_CORRUPT_PACK))

    rc = run(_app(data_root), ["job", "create", "--manifest", str(manifest)], out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == ["CORRUPT_REFERENCE_PACK"]
    _assert_no_absolute_root(payload, data_root)


def test_mcp_create_job_maps_a_missing_reference_pack(data_root: Path) -> None:
    handlers = make_handlers(_app(data_root))

    result = handlers["create_job"](manifest=_manifest_payload(_MISSING_PACK))

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert structured["ok"] is False
    assert [diagnostic["code"] for diagnostic in diagnostics] == ["UNKNOWN_REFERENCE_PACK"]
    _assert_no_absolute_root(json.dumps(result.model_dump(mode="json")), data_root)


def test_mcp_create_job_maps_a_corrupt_reference_pack(data_root: Path) -> None:
    _corrupt_pack(data_root)
    handlers = make_handlers(_app(data_root))

    result = handlers["create_job"](manifest=_manifest_payload(_CORRUPT_PACK))

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert structured["ok"] is False
    assert [diagnostic["code"] for diagnostic in diagnostics] == ["CORRUPT_REFERENCE_PACK"]
    _assert_no_absolute_root(json.dumps(result.model_dump(mode="json")), data_root)


def test_no_job_is_persisted_when_the_reference_pack_is_unusable(data_root: Path) -> None:
    client = TestClient(create_api(_app(data_root)))

    client.post("/api/jobs", json=_manifest_payload(_MISSING_PACK))

    assert client.get("/api/jobs").json() == []


def _derived_manifest_payload(parent_asset_id: str | None) -> dict[str, object]:
    return {
        "version": "1.0",
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "expression_refine",
        "provider": "fake",
        "character_ref_pack": None,
        "character_ref_pack_rev": None,
        "parent_asset_id": parent_asset_id,
        "sources": [{"kind": "approved_portrait", "ref": "hero.png"}],
        "edit": None,
        "params": {},
    }


def test_http_create_job_refuses_an_unknown_parent_asset(data_root: Path) -> None:
    """The approved base is checked before a provider ever runs."""
    client = TestClient(create_api(_app(data_root)))

    response = client.post("/api/jobs", json=_derived_manifest_payload("not-an-asset"))

    assert response.status_code == 404
    assert [diagnostic["code"] for diagnostic in response.json()] == ["UNKNOWN_LINEAGE"]
    assert response.json()[0]["where"] == "not-an-asset"
    assert client.get("/api/jobs").json() == []
    _assert_no_absolute_root(response.text, data_root)


def test_cli_create_job_refuses_an_unknown_parent_asset(data_root: Path, tmp_path: Path) -> None:
    out = io.StringIO()
    manifest = _manifest_file(tmp_path, _derived_manifest_payload("not-an-asset"))

    rc = run(_app(data_root), ["job", "create", "--manifest", str(manifest)], out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == ["UNKNOWN_LINEAGE"]
    _assert_no_absolute_root(payload, data_root)


def test_mcp_create_job_refuses_an_unknown_parent_asset(data_root: Path) -> None:
    handlers = make_handlers(_app(data_root))

    result = handlers["create_job"](manifest=_derived_manifest_payload("not-an-asset"))

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert [diagnostic["code"] for diagnostic in diagnostics] == ["UNKNOWN_LINEAGE"]
    _assert_no_absolute_root(json.dumps(result.model_dump(mode="json")), data_root)


def test_create_job_accepts_a_known_parent_asset(data_root: Path) -> None:
    from fecreator.contracts.lineage import LineageNode, Operation
    from fecreator.lineage.store import LineageStore

    LineageStore(data_root).add(
        LineageNode(
            asset_id="approved-base",
            operation=Operation.CREATE_NEUTRAL,
            created_at="2026-07-26T00:00:00+00:00",
        )
    )
    client = TestClient(create_api(_app(data_root)))

    response = client.post("/api/jobs", json=_derived_manifest_payload("approved-base"))

    assert response.status_code == 201
    assert response.json()["manifest"]["parent_asset_id"] == "approved-base"


def _corrupt_job_store(data_root: Path) -> None:
    from fecreator.contracts.manifest import Manifest

    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload(None)))
    (data_root / "jobs" / job.id / "job.json").write_text("{", encoding="utf-8")


def test_http_maps_a_corrupt_job_store_without_disclosing_the_data_root(data_root: Path) -> None:
    _corrupt_job_store(data_root)
    client = TestClient(create_api(_app(data_root)))

    response = client.get("/api/jobs")

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == ["CORRUPT_JOB"]
    _assert_no_absolute_root(response.text, data_root)


def test_cli_maps_a_corrupt_job_store_without_disclosing_the_data_root(data_root: Path) -> None:
    _corrupt_job_store(data_root)
    out = io.StringIO()

    rc = run(_app(data_root), ["job", "list"], out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == ["CORRUPT_JOB"]
    _assert_no_absolute_root(payload, data_root)


def test_mcp_maps_a_corrupt_job_store_without_disclosing_the_data_root(data_root: Path) -> None:
    _corrupt_job_store(data_root)
    handlers = make_handlers(_app(data_root))

    result = handlers["list_jobs"]()

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert [diagnostic["code"] for diagnostic in diagnostics] == ["CORRUPT_JOB"]
    _assert_no_absolute_root(json.dumps(result.model_dump(mode="json")), data_root)
