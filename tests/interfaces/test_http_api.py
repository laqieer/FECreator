from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import fecreator.interfaces.http_api as http_api
from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import error
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.core.config import Settings
from fecreator.core.hashing import sha256_file
from fecreator.interfaces import static as static_module
from fecreator.interfaces.http_api import create_api
from fecreator.lineage.store import LineageStore
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore
from tests.dialogue_background.conftest import assert_delivered_truecolor_background_png

pytest_plugins = ("tests.dialogue_background.conftest",)


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


def _dialogue_background_manifest_payload() -> dict[str, object]:
    return {
        "asset_type": "dialogue_background",
        "target_spec": "fe8-dialogue-background-source-240x160",
        "workflow": "text_to_dialogue_background",
        "provider": "manual",
        "metadata": {
            "name": "phantom_city",
            "purpose": "Original phantom city",
            "source": {"kind": "prompt", "id": "bg/phantom-city", "revision": "1"},
            "license_note": "Original repository fixture.",
            "source_note": "Generated from an original prompt.",
        },
        "sources": [{"kind": "text", "ref": "phantom city"}],
        "params": {"width": 240, "height": 160},
    }


def test_http_manual_dialogue_background_completes_from_truecolor_upload(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    truecolor_background_sources: Path,
) -> None:
    source = truecolor_background_sources / "phantom_city.png"
    assert_delivered_truecolor_background_png(source.read_bytes())

    app = _app(data_root)
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    with TestClient(create_api(app)) as client:
        created = client.post("/api/jobs", json=_dialogue_background_manifest_payload())
        job_id = created.json()["id"]
        plan = client.post(f"/api/jobs/{job_id}/plan-sources")
        submitted = client.post(
            f"/api/jobs/{job_id}/sources",
            files=[("files", ("phantom_city.png", source.read_bytes(), "image/png"))],
        )
        built = client.post(f"/api/jobs/{job_id}/build")
        waiting = client.get(f"/api/jobs/{job_id}")
        approval = client.post(f"/api/jobs/{job_id}/approve", json={"actor": "reviewer"})
        finalized = client.post(f"/api/jobs/{job_id}/finalize")
        completed = client.get(f"/api/jobs/{job_id}")
        png_artifact = client.get(f"/api/jobs/{job_id}/artifacts/package/phantom_city.png")
        manifest_artifact = client.get(
            f"/api/jobs/{job_id}/artifacts/package/phantom_city.manifest.json"
        )
        report = client.get(f"/api/jobs/{job_id}/report")
        bundle = client.get(f"/api/jobs/{job_id}/bundle")
        compat = client.get(f"/api/jobs/{job_id}/bundle/compat.json")

    assert created.status_code == 201
    assert plan.status_code == 200
    assert plan.json()["expected_filenames"] == ["phantom_city.png"]
    assert submitted.status_code == 200
    assert submitted.json()["state"] == "waiting_for_sources"
    assert built.status_code == 200
    assert built.json()["ok"] is True
    assert waiting.json()["state"] == "waiting_for_review"
    assert approval.status_code == 200
    assert approval.json()["decision"] == "approved"
    assert finalized.status_code == 200
    assert finalized.json()["ok"] is True
    assert completed.json()["state"] == "completed"
    assert png_artifact.status_code == manifest_artifact.status_code == 200
    workspace = data_root / "jobs" / job_id / "package"
    package_manifest = json.loads(manifest_artifact.content)
    assert package_manifest["png_sha256"] == sha256_file(workspace / "phantom_city.png")
    assert png_artifact.content == (workspace / "phantom_city.png").read_bytes()
    assert_delivered_truecolor_background_png(png_artifact.content)
    assert report.status_code == 200
    assert report.json()["manifest"]["asset_type"] == "dialogue_background"
    assert {node["operation"] for node in report.json()["lineage"]} == {
        "create_dialogue_background",
        "export_spec",
    }
    assert bundle.status_code == 200
    assert compat.status_code == 200
    assert {entry["path"] for entry in bundle.json() if entry["path"].startswith("package/")} == {
        "package/phantom_city.png",
        "package/phantom_city.manifest.json",
    }
    assert json.loads(compat.content)["external_adapter"] == {"status": "not_run", "profile": None}


async def test_specs_endpoint(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with _client(data_root, monkeypatch) as client:
        resp = await client.get("/api/specs")

    assert resp.status_code == 200
    assert resp.json() == [
        "fe-gba-portrait-standard",
        "fe8-dialogue-background-source-240x160",
    ]


async def test_create_and_get_job(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with _client(data_root, monkeypatch) as client:
        created = await client.post("/api/jobs", json=_manifest_payload())
        fetched = await client.get(f"/api/jobs/{created.json()['id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "created"


async def test_additive_read_routes_use_the_application_facade(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))
    workspace = data_root / "jobs" / job.id
    (workspace / "package").mkdir()
    (workspace / "package" / "portrait.png").write_bytes(b"portrait")
    (workspace / "bundle").mkdir()
    (workspace / "bundle" / "manifest.json").write_text("{}", encoding="utf-8")
    (workspace / "report.json").write_text(
        '{"path":"C:\\\\private\\\\report.json"}',
        encoding="utf-8",
    )
    ReferencePackStore(data_root).create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    LineageStore(data_root).add(
        LineageNode(
            asset_id="hero-export",
            operation=Operation.EXPORT_SPEC,
            created_at="2026-07-26T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        jobs = await client.get("/api/jobs")
        candidate = await client.get(f"/api/jobs/{job.id}/candidate")
        approvals = await client.get(f"/api/jobs/{job.id}/approvals")
        plan = await client.post(f"/api/jobs/{job.id}/plan-sources")
        validation = await client.post(f"/api/jobs/{job.id}/validate")
        artifact = await client.get(f"/api/jobs/{job.id}/artifacts/package/portrait.png")
        report = await client.get(f"/api/jobs/{job.id}/report")
        bundle = await client.get(f"/api/jobs/{job.id}/bundle")
        bundle_file = await client.get(f"/api/jobs/{job.id}/bundle/manifest.json")
        references = await client.get("/api/references")
        history = await client.get("/api/references/hero-pack/history")
        lineage = await client.get("/api/lineage/hero-export")
        ancestors = await client.get("/api/lineage/hero-export/ancestors")
        children = await client.get("/api/lineage/hero-export/children")

    assert jobs.status_code == 200
    assert [item["id"] for item in jobs.json()] == [job.id]
    assert candidate.status_code == 404
    assert candidate.json()[0]["code"] == "CANDIDATE_NOT_FOUND"
    assert approvals.status_code == 200
    assert approvals.json() == []
    assert plan.status_code == 200
    assert "neutral.png" in plan.json()["expected_filenames"]
    assert validation.status_code == 200
    assert validation.json()[0]["code"] == "BAD_PNG"
    assert artifact.status_code == 200
    assert artifact.content == b"portrait"
    assert report.json() == {"path": "report.json"}
    assert bundle.json() == [{"path": "manifest.json", "size_bytes": 2}]
    assert bundle_file.content == b"{}"
    assert references.json() == ["hero-pack"]
    assert [item["revision"] for item in history.json()] == [1]
    assert lineage.json()["asset_id"] == "hero-export"
    assert ancestors.json() == []
    assert children.json() == []


async def test_http_source_upload_enforces_budgets_and_removes_staging(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate({**_manifest_payload(), "provider": "manual"}))
    app.plan_job_sources(job.id)
    called_with: list[Path] = []
    original_submit_sources = app.submit_sources

    def submit_sources(job_id: str, sources_dir: Path):
        called_with.append(sources_dir)
        assert sources_dir.is_dir()
        return original_submit_sources(job_id, sources_dir)

    monkeypatch.setattr(app, "submit_sources", submit_sources)
    monkeypatch.setattr(http_api, "MAX_UPLOAD_FILE_BYTES", 3)
    monkeypatch.setattr(http_api, "MAX_UPLOAD_TOTAL_BYTES", 3)
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))
    files = [("files", ("neutral.png", b"ok", "image/png"))]

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(f"/api/jobs/{job.id}/sources", files=files)
        oversized = await client.post(
            f"/api/jobs/{job.id}/sources",
            files=[("files", ("again.png", b"four", "image/png"))],
        )
        duplicate = await client.post(
            f"/api/jobs/{job.id}/sources",
            files=[
                ("files", ("same.png", b"a", "image/png")),
                ("files", ("same.png", b"b", "image/png")),
            ],
        )
        unsafe = await client.post(
            f"/api/jobs/{job.id}/sources",
            files=[("files", ("../escape.png", b"a", "image/png"))],
        )
        total = await client.post(
            f"/api/jobs/{job.id}/sources",
            files=[
                ("files", ("first.png", b"aa", "image/png")),
                ("files", ("second.png", b"bb", "image/png")),
            ],
        )

    assert submitted.status_code == 200
    assert submitted.json()["state"] == "waiting_for_sources"
    assert oversized.status_code == 422
    assert oversized.json()[0]["code"] == "UPLOAD_FILE_LIMIT"
    assert duplicate.status_code == 422
    assert duplicate.json()[0]["code"] == "UPLOAD_DUPLICATE_NAME"
    assert unsafe.status_code == 422
    assert unsafe.json()[0]["code"] == "UPLOAD_UNSAFE_NAME"
    assert total.status_code == 422
    assert total.json()[0]["code"] == "UPLOAD_TOTAL_LIMIT"
    assert len(called_with) == 1
    assert not called_with[0].exists()


async def test_review_routes_report_unknown_jobs_and_invalid_states_as_diagnostics(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        unknown = await client.post("/api/jobs/missing/approve", json={"actor": "reviewer"})
        invalid_state = await client.post(
            f"/api/jobs/{job.id}/approve",
            json={"actor": "reviewer"},
        )

    assert unknown.status_code == 404
    assert unknown.json()[0]["code"] == "UNKNOWN_JOB"
    assert invalid_state.status_code == 409
    assert invalid_state.json()[0]["code"] == "APPROVE_REVIEW_FAILED"


async def test_build_route_reports_unknown_jobs_and_invalid_states_as_diagnostics(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        unknown = await client.post("/api/jobs/missing/build")
        built = await client.post(f"/api/jobs/{job.id}/build")
        invalid_state = await client.post(f"/api/jobs/{job.id}/build")

    assert unknown.status_code == 404
    assert unknown.json()[0]["code"] == "UNKNOWN_JOB"
    assert built.status_code == 200
    assert invalid_state.status_code == 409
    assert invalid_state.json()[0]["code"] == "BUILD_ASSET_FAILED"


async def test_build_route_returns_expected_build_failure_result(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))
    expected = JobResult(
        job_id=job.id,
        ok=False,
        diagnostics=(error("BUILD_REJECTED", "provider rejected the build", where=job.id),),
    )
    monkeypatch.setattr(app, "build", lambda _job_id: expected)
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/jobs/{job.id}/build")

    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")


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


async def test_reference_routes_map_store_corruption_to_structured_diagnostics(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    ReferencePackStore(data_root).create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    (data_root / "refs" / "locks").mkdir()
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid_id = await client.get("/api/references")
        (data_root / "refs" / "locks").rmdir()
        (data_root / "refs" / "hero-pack" / "1.json").rename(
            data_root / "refs" / "hero-pack" / "2.json"
        )
        corrupt_list = await client.get("/api/references")
        corrupt_history = await client.get("/api/references/hero-pack/history")

    assert invalid_id.status_code == 409
    assert invalid_id.json() == [
        {
            "code": "CORRUPT_REFERENCE_PACK",
            "data": None,
            "message": "reference pack store is corrupt",
            "severity": "error",
            "where": "references",
        }
    ]
    assert corrupt_list.status_code == 409
    assert corrupt_list.json()[0]["code"] == "CORRUPT_REFERENCE_PACK"
    assert corrupt_history.status_code == 409
    assert corrupt_history.json() == [
        {
            "code": "CORRUPT_REFERENCE_PACK",
            "data": None,
            "message": "reference pack is corrupt",
            "severity": "error",
            "where": "hero-pack",
        }
    ]


def _multipart_body(
    filename: str,
    payload: bytes,
    *,
    boundary: str = "fecreatorboundary",
) -> bytes:
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("ascii")
    return header + payload + f"\r\n--{boundary}--\r\n".encode("ascii")


def _multipart_headers(boundary: str = "fecreatorboundary") -> dict[str, str]:
    return {"content-type": f"multipart/form-data; boundary={boundary}"}


def _staging_dirs(workspace: Path) -> list[Path]:
    return [entry for entry in workspace.iterdir() if entry.name.startswith(".http-upload-")]


async def test_source_upload_rejects_oversized_request_bodies_before_parsing(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate({**_manifest_payload(), "provider": "manual"}))
    app.plan_job_sources(job.id)
    workspace = data_root / "jobs" / job.id
    monkeypatch.setattr(http_api, "MAX_UPLOAD_REQUEST_BYTES", 512)
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))
    body = _multipart_body("neutral.png", b"x" * 4096)

    async def _stream_body():
        for start in range(0, len(body), 64):
            yield body[start : start + 64]

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        declared = await client.post(
            f"/api/jobs/{job.id}/sources",
            content=body,
            headers=_multipart_headers(),
        )
        monkeypatch.setattr(
            http_api.UploadRequestSizeLimiter,
            "_declared_length",
            staticmethod(lambda _scope: 0),
        )
        streamed = await client.post(
            f"/api/jobs/{job.id}/sources",
            content=_stream_body(),
            headers=_multipart_headers(),
        )
        understated = await client.post(
            f"/api/jobs/{job.id}/sources",
            content=_stream_body(),
            headers={**_multipart_headers(), "content-length": "16"},
        )

    assert declared.status_code == 422
    assert declared.json() == [
        {
            "code": "UPLOAD_REQUEST_LIMIT",
            "data": None,
            "message": "upload request exceeds the byte limit",
            "severity": "error",
            "where": "files",
        }
    ]
    assert streamed.status_code == 422
    assert streamed.json() == declared.json()
    assert understated.status_code == 422
    assert understated.json() == declared.json()
    assert app.get_job(job.id).state.value == "waiting_for_sources"
    assert not (workspace / "submitted").exists()
    assert _staging_dirs(workspace) == []


async def test_source_upload_rejects_windows_reserved_and_trailing_dot_filenames(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate({**_manifest_payload(), "provider": "manual"}))
    app.plan_job_sources(job.id)
    workspace = data_root / "jobs" / job.id
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        responses = [
            await client.post(
                f"/api/jobs/{job.id}/sources",
                files=[("files", (filename, b"png-bytes", "image/png"))],
            )
            for filename in ("CON.png", "con.png", "nul", "lpt9.png", "neutral.png.")
        ]

    assert [response.status_code for response in responses] == [422, 422, 422, 422, 422]
    assert {response.json()[0]["code"] for response in responses} == {"UPLOAD_UNSAFE_NAME"}
    assert not (workspace / "submitted").exists()
    assert _staging_dirs(workspace) == []


async def test_artifact_reads_are_scoped_to_packages_and_reject_backslash_paths(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(data_root)
    job = app.create_job(Manifest.model_validate(_manifest_payload()))
    workspace = data_root / "jobs" / job.id
    (workspace / "package").mkdir()
    (workspace / "package" / "portrait.png").write_bytes(b"portrait")
    (workspace / "bundle").mkdir()
    (workspace / "bundle" / "manifest.json").write_text("{}", encoding="utf-8")
    (workspace / "report.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(static_module, "web_dir", lambda: None)
    transport = httpx.ASGITransport(app=create_api(app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        allowed = await client.get(f"/api/jobs/{job.id}/artifacts/package/portrait.png")
        blocked = [
            await client.get(f"/api/jobs/{job.id}/artifacts/{relative_path}")
            for relative_path in (
                "job.json",
                "manifest.json",
                "events.jsonl",
                "report.json",
                "bundle/manifest.json",
            )
        ]
        backslash_artifact = await client.get(
            f"/api/jobs/{job.id}/artifacts/package%5Cportrait.png"
        )
        backslash_bundle = await client.get(f"/api/jobs/{job.id}/bundle/..%5Creport.json")

    assert allowed.status_code == 200
    assert [response.status_code for response in blocked] == [404, 404, 404, 404, 404]
    assert {response.json()[0]["code"] for response in blocked} == {"READ_ARTIFACT_FAILED"}
    assert str(data_root) not in blocked[0].text
    assert backslash_artifact.status_code == 404
    assert backslash_artifact.json()[0]["code"] == "READ_ARTIFACT_FAILED"
    assert backslash_bundle.status_code == 404
    assert backslash_bundle.json()[0]["code"] == "READ_BUNDLE_FILE_FAILED"
