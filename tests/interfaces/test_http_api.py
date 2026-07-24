from fastapi.testclient import TestClient

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api


def _client(tmp_path):  # type: ignore[no-untyped-def]
    return TestClient(create_api(FeCreatorApp(Settings(data_root=tmp_path))))


def test_specs_endpoint(tmp_path):  # type: ignore[no-untyped-def]
    resp = _client(tmp_path).get("/api/specs")
    assert resp.status_code == 200
    assert "fe-gba-portrait-standard" in resp.json()


def test_create_and_get_job(tmp_path):  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    body = {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": "fake",
        "sources": [{"kind": "text", "ref": "hero"}],
    }
    created = client.post("/api/jobs", json=body).json()
    fetched = client.get(f"/api/jobs/{created['id']}")
    assert fetched.status_code == 200 and fetched.json()["state"] == "created"


def test_get_missing_job_is_404(tmp_path):  # type: ignore[no-untyped-def]
    assert _client(tmp_path).get("/api/jobs/nope").status_code == 404


def test_validate_job_reports_missing_sheet(tmp_path):  # type: ignore[no-untyped-def]
    """Validate job workspace (no arbitrary server paths accepted)."""
    client = _client(tmp_path)
    body = {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": "fake",
        "sources": [],
    }
    job_id = client.post("/api/jobs", json=body).json()["id"]
    resp = client.post(
        f"/api/jobs/{job_id}/validate",
        json={"spec_id": "fe-gba-portrait-standard"},
    )
    assert resp.status_code == 200
    assert any(d["code"] == "MISSING_SHEET" for d in resp.json())


def test_validate_job_unknown_spec_returns_422(tmp_path):  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    body = {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": "fake",
        "sources": [],
    }
    job_id = client.post("/api/jobs", json=body).json()["id"]
    resp = client.post(f"/api/jobs/{job_id}/validate", json={"spec_id": "no-such-spec"})
    assert resp.status_code == 422


def test_cancel_endpoint_409_if_already_cancelled(tmp_path):  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    body = {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": "fake",
        "sources": [],
    }
    job_id = client.post("/api/jobs", json=body).json()["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 409  # already cancelled


def test_missing_job_build_returns_404(tmp_path):  # type: ignore[no-untyped-def]
    resp = _client(tmp_path).post("/api/jobs/nonexistent/build")
    assert resp.status_code == 404
