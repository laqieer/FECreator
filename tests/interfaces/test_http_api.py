from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces import static as static_module
from fecreator.interfaces.http_api import create_api


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    static_dir: Path | None = None,
) -> httpx.AsyncClient:
    monkeypatch.setattr(static_module, "web_dir", lambda: static_dir)
    transport = httpx.ASGITransport(app=create_api(_app(data_root)))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _manifest_payload() -> dict[str, object]:
    return {
        "asset_type": "portrait",
        "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait",
        "provider": "fake",
        "sources": [{"kind": "text", "ref": "hero"}],
    }


async def test_specs_endpoint(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.get("/api/specs")

    assert resp.status_code == 200
    assert resp.json() == ["fe-gba-portrait-standard"]


async def test_create_and_get_job(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with _client(data_root, monkeypatch) as client:
        created = await client.post("/api/jobs", json=_manifest_payload())
        fetched = await client.get(f"/api/jobs/{created.json()['id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "created"


async def test_get_missing_job_returns_deterministic_404_diagnostic(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.get("/api/jobs/nope")

    assert resp.status_code == 404
    assert resp.json() == [
        {
            "code": "UNKNOWN_JOB",
            "data": None,
            "message": "job not found",
            "severity": "error",
            "where": "nope",
        }
    ]


async def test_validate_endpoint_reports_missing_sheet(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.post(
            "/api/validate",
            json={"spec_id": "fe-gba-portrait-standard", "package_dir": str(tmp_path)},
        )

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "code": "MISSING_SHEET",
            "data": None,
            "message": "package has no PNG",
            "severity": "error",
            "where": tmp_path.name,
        }
    ]


async def test_validate_unknown_spec_returns_deterministic_404_diagnostic(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.post(
            "/api/validate",
            json={"spec_id": "missing-spec", "package_dir": str(tmp_path)},
        )

    assert resp.status_code == 404
    assert resp.json() == [
        {
            "code": "UNKNOWN_SPEC",
            "data": None,
            "message": "unknown target spec",
            "severity": "error",
            "where": "missing-spec",
        }
    ]


@pytest.mark.parametrize(
    ("payload", "error_count"),
    [
        ({"spec_id": "", "package_dir": "package"}, 1),
        ({"spec_id": "fe-gba-portrait-standard", "package_dir": ""}, 1),
        ({"spec_id": " ", "package_dir": " "}, 2),
    ],
)
async def test_validate_rejects_blank_fields_with_deterministic_422_diagnostic(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, str],
    error_count: int,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.post("/api/validate", json=payload)

    assert resp.status_code == 422
    assert resp.json() == [
        {
            "code": "INVALID_REQUEST",
            "data": {"error_count": error_count},
            "message": "request failed validation",
            "severity": "error",
            "where": "api/validate",
        }
    ]


async def test_create_job_rejects_extra_fields_with_deterministic_422_diagnostic(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.post(
            "/api/jobs",
            json={**_manifest_payload(), "unexpected": "value"},
        )

    assert resp.status_code == 422
    assert resp.json() == [
        {
            "code": "INVALID_REQUEST",
            "data": {"error_count": 1},
            "message": "request failed validation",
            "severity": "error",
            "where": "api/jobs",
        }
    ]


@pytest.mark.parametrize(
    ("job_path", "where"),
    [
        ("/api/jobs/%2E%2E", ".."),
        ("/api/jobs/%20%20", "  "),
    ],
)
async def test_get_job_rejects_invalid_ids_with_deterministic_404_diagnostic(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    job_path: str,
    where: str,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.get(job_path)

    assert resp.status_code == 404
    assert resp.json() == [
        {
            "code": "UNKNOWN_JOB",
            "data": None,
            "message": "job not found",
            "severity": "error",
            "where": where,
        }
    ]


def test_web_dir_requires_built_index_html(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "package"
    web_assets = package_dir / "_web"
    web_assets.mkdir(parents=True)
    monkeypatch.setattr(static_module.resources, "files", lambda _package: package_dir)

    assert static_module.web_dir() is None

    (web_assets / "index.html").write_text("<!doctype html><title>ui</title>", encoding="utf-8")

    assert static_module.web_dir() == web_assets


def test_web_dir_rejects_symlinked_asset_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    actual_assets = tmp_path / "actual-assets"
    actual_assets.mkdir()
    (actual_assets / "index.html").write_text("<!doctype html><title>ui</title>", encoding="utf-8")
    try:
        (package_dir / "_web").symlink_to(actual_assets, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    monkeypatch.setattr(static_module.resources, "files", lambda _package: package_dir)

    assert static_module.web_dir() is None


async def test_root_returns_clear_503_when_packaged_web_assets_are_missing(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.get("/")

    assert resp.status_code == 503
    assert resp.text == (
        "Packaged web assets are unavailable. "
        "Run `npm run -w @laqieer/fecreator-web build` to build them."
    )


async def test_root_serves_packaged_index_when_assets_are_present(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    web_assets = tmp_path / "_web"
    web_assets.mkdir()
    (web_assets / "index.html").write_text(
        "<!doctype html><html><body>FECreator UI</body></html>",
        encoding="utf-8",
    )

    async with _client(data_root, monkeypatch, static_dir=web_assets) as client:
        resp = await client.get("/")

    assert resp.status_code == 200
    assert "FECreator UI" in resp.text
