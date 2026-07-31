"""Lock contention must surface as a structured, redacted conflict everywhere.

Releasing the job lock across provider execution makes contention rare, but it
cannot make it impossible. Whatever remains has to reach CLI, HTTP, MCP, and
WebSocket clients as an ordinary structured failure, never as a stack trace or a
message quoting the absolute data root.
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.atomicio import LockTimeoutError
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import run
from fecreator.interfaces.http_api import create_api
from fecreator.interfaces.mcp_server import make_handlers
from fecreator.jobs.model import Job

LOCK_TIMEOUT_CODE = "STORE_LOCK_TIMEOUT"


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _contended_app(data_root: Path) -> tuple[FeCreatorApp, Job, str]:
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    lock_path = data_root / "jobs" / job.id / "job.json"
    sidecar = data_root / "jobs" / ".locks" / f"{job.id}.lock"
    message = f"timed out acquiring lock for {lock_path} via {sidecar}"

    def raise_lock_timeout(*_args: object, **_kwargs: object) -> Job:
        raise LockTimeoutError(message)

    app.get_job = raise_lock_timeout  # type: ignore[method-assign]
    return app, job, str(data_root)


def _assert_redacted(payload: str, data_root: str) -> None:
    assert data_root not in payload
    assert data_root.replace("\\", "/") not in payload
    assert data_root.replace("\\", "\\\\") not in payload


def test_http_maps_job_lock_contention_to_a_redacted_conflict(data_root: Path) -> None:
    app, job, root = _contended_app(data_root)
    client = TestClient(create_api(app))

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == [LOCK_TIMEOUT_CODE]
    assert all(diagnostic["severity"] == "error" for diagnostic in response.json())
    _assert_redacted(response.text, root)


def test_cli_maps_job_lock_contention_to_a_redacted_conflict(data_root: Path) -> None:
    app, job, root = _contended_app(data_root)
    out = io.StringIO()

    rc = run(app, ["job", "status", job.id], out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(payload, root)


def test_mcp_maps_job_lock_contention_to_a_redacted_conflict(data_root: Path) -> None:
    app, job, root = _contended_app(data_root)
    handlers = make_handlers(app)

    result = handlers["get_job"](job_id=job.id)

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert structured["ok"] is False
    assert [diagnostic["code"] for diagnostic in diagnostics] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(json.dumps(result.model_dump(mode="json")), root)


def test_websocket_closes_with_try_again_later_on_lock_contention(data_root: Path) -> None:
    app, job, _root = _contended_app(data_root)
    client = TestClient(create_api(app))

    with (
        client.websocket_connect(f"/ws/jobs/{job.id}") as ws,
        pytest.raises(WebSocketDisconnect) as exc_info,
    ):
        ws.receive_json()

    assert exc_info.value.code == 1013


def test_websocket_reads_storage_off_the_event_loop_thread(data_root: Path) -> None:
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    observed: list[bool] = []
    real_get_job = app.get_job

    def record_thread(job_id: str) -> Job:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            observed.append(True)
        else:
            observed.append(False)
        return real_get_job(job_id)

    app.get_job = record_thread  # type: ignore[method-assign]
    client = TestClient(create_api(app))

    with client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        message = ws.receive_json()

    assert message["job_id"] == job.id
    assert observed == [True]


def test_job_reads_do_not_block_forever_behind_a_held_lock(data_root: Path) -> None:
    """A real held lock still ends in a structured conflict, never a traceback."""
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    holding = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with app._jobs.locked(job.id):
            holding.set()
            assert release.wait(timeout=30)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert holding.wait(timeout=10)
    client = TestClient(create_api(app))
    try:
        response = client.get(f"/api/jobs/{job.id}")
    finally:
        release.set()
        holder.join(timeout=10)

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(response.text, str(data_root))


_BROADLY_HANDLED_OPERATIONS = (
    "validate_job",
    "finalize_job",
    "plan_job_sources",
    "build",
    "list_bundle_entries",
)


def _app_raising_lock_timeout(data_root: Path, operation: str) -> tuple[FeCreatorApp, Job, str]:
    """Force one app operation to fail with contention, keeping ``get_job`` usable."""
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    lock_path = data_root / "jobs" / job.id / "job.json"
    message = f"timed out acquiring lock for {lock_path} via {lock_path}.lock"

    def raise_lock_timeout(*_args: object, **_kwargs: object) -> object:
        raise LockTimeoutError(message)

    setattr(app, operation, raise_lock_timeout)
    return app, job, str(data_root)


@pytest.mark.parametrize("operation", _BROADLY_HANDLED_OPERATIONS)
def test_http_reports_lock_contention_even_where_oserror_is_handled_broadly(
    data_root: Path, operation: str
) -> None:
    """``LockTimeoutError`` is an ``OSError``; broad handlers must not absorb it."""
    app, job, root = _app_raising_lock_timeout(data_root, operation)
    client = TestClient(create_api(app))
    routes = {
        "validate_job": ("post", f"/api/jobs/{job.id}/validate"),
        "finalize_job": ("post", f"/api/jobs/{job.id}/finalize"),
        "plan_job_sources": ("post", f"/api/jobs/{job.id}/plan-sources"),
        "build": ("post", f"/api/jobs/{job.id}/build"),
        "list_bundle_entries": ("get", f"/api/jobs/{job.id}/bundle"),
    }
    method, path = routes[operation]

    response = getattr(client, method)(path)

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(response.text, root)


@pytest.mark.parametrize("operation", _BROADLY_HANDLED_OPERATIONS)
def test_cli_reports_lock_contention_even_where_oserror_is_handled_broadly(
    data_root: Path, operation: str
) -> None:
    app, job, root = _app_raising_lock_timeout(data_root, operation)
    argv = {
        "validate_job": ["job", "validate", job.id],
        "finalize_job": ["job", "finalize", job.id],
        "plan_job_sources": ["job", "plan-sources", job.id],
        "build": ["build", "--job", job.id],
        "list_bundle_entries": ["job", "bundle", job.id],
    }[operation]
    out = io.StringIO()

    rc = run(app, argv, out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(payload, root)


@pytest.mark.parametrize("operation", _BROADLY_HANDLED_OPERATIONS)
def test_mcp_reports_lock_contention_even_where_oserror_is_handled_broadly(
    data_root: Path, operation: str
) -> None:
    app, job, root = _app_raising_lock_timeout(data_root, operation)
    handlers = make_handlers(app)
    tool = {
        "validate_job": "validate_job",
        "finalize_job": "finalize_job",
        "plan_job_sources": "plan_job_sources",
        "build": "build_asset",
        "list_bundle_entries": "list_bundle_entries",
    }[operation]

    result = handlers[tool](job_id=job.id)

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert [diagnostic["code"] for diagnostic in diagnostics] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(json.dumps(result.model_dump(mode="json")), root)


def _build_with_contended_job_lock(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[FeCreatorApp, Job, str]:
    """Run a real build whose short claim transition hits a held job lock.

    The build lease is acquired successfully, so this is *not* a second build;
    it is ordinary contention raised from inside the lease body. Before this
    wave the lease relabelled it as ``InvalidTransitionError`` and the adapters
    reported ``BUILD_ASSET_FAILED``.
    """
    import fecreator.assets.reviewed as reviewed_module
    from fecreator.jobs.store import JobStore

    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    lock_path = data_root / "jobs" / job.id / "job.json"
    message = f"timed out acquiring lock for {lock_path} via {lock_path}.lock"

    class _ContendedStore(JobStore):
        def locked(self, job_id: str):  # type: ignore[no-untyped-def]
            raise LockTimeoutError(message)

    monkeypatch.setattr(reviewed_module, "JobStore", _ContendedStore)
    return app, job, str(data_root)


def test_cli_build_reports_job_lock_contention_from_inside_the_build_lease(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, job, root = _build_with_contended_job_lock(data_root, monkeypatch)
    out = io.StringIO()

    rc = run(app, ["build", "--job", job.id], out)

    payload = out.getvalue()
    assert rc == 2
    assert [diagnostic["code"] for diagnostic in json.loads(payload)] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(payload, root)


def test_mcp_build_reports_job_lock_contention_from_inside_the_build_lease(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, job, root = _build_with_contended_job_lock(data_root, monkeypatch)
    handlers = make_handlers(app)

    result = handlers["build_asset"](job_id=job.id)

    structured = cast(dict[str, object], result.structuredContent)
    diagnostics = cast(list[dict[str, object]], structured["diagnostics"])
    assert result.isError is True
    assert [diagnostic["code"] for diagnostic in diagnostics] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(json.dumps(result.model_dump(mode="json")), root)


def test_job_listing_reports_a_held_lock_as_contention_not_corruption(data_root: Path) -> None:
    """Listing must never advise deleting a job that is merely locked."""
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_manifest())
    holding = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with app._jobs.locked(job.id):
            holding.set()
            assert release.wait(timeout=30)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert holding.wait(timeout=10)
    client = TestClient(create_api(app))
    try:
        response = client.get("/api/jobs")
    finally:
        release.set()
        holder.join(timeout=10)

    assert response.status_code == 409
    assert [diagnostic["code"] for diagnostic in response.json()] == [LOCK_TIMEOUT_CODE]
    _assert_redacted(response.text, str(data_root))
