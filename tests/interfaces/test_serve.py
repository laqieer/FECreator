from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from fecreator.cli import main
from fecreator.interfaces import static as static_module


@pytest.fixture()
def captured_uvicorn(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_run(api: FastAPI, **kwargs: Any) -> None:
        captured["api"] = api
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return captured


@pytest.fixture()
def serve_env(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FECREATOR_DATA_ROOT", str(data_root))
    monkeypatch.delenv("FECREATOR_HOST", raising=False)
    monkeypatch.delenv("FECREATOR_PORT", raising=False)
    return data_root


def test_serve_binds_configured_localhost(
    serve_env: Path,
    captured_uvicorn: dict[str, Any],
) -> None:
    assert main(["serve"]) == 0
    assert captured_uvicorn["host"] == "127.0.0.1"
    assert captured_uvicorn["port"] == 8765


def test_serve_uses_the_configured_loopback_host_and_port(
    serve_env: Path,
    captured_uvicorn: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FECREATOR_HOST", "localhost")
    monkeypatch.setenv("FECREATOR_PORT", "8791")

    assert main(["serve"]) == 0
    assert captured_uvicorn["host"] == "localhost"
    assert captured_uvicorn["port"] == 8791


async def test_serve_mounts_the_api_and_the_packaged_web_assets(
    serve_env: Path,
    captured_uvicorn: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assets = tmp_path / "_web"
    (assets / "assets").mkdir(parents=True)
    index_html = "<!doctype html><title>FECreator</title>\n"
    (assets / "index.html").write_text(index_html, encoding="utf-8", newline="\n")
    (assets / "assets" / "app.js").write_text("export {};\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(static_module, "web_dir", lambda: assets)

    assert main(["serve"]) == 0

    api = captured_uvicorn["api"]
    assert isinstance(api, FastAPI)

    transport = httpx.ASGITransport(app=api)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        specs = await client.get("/api/specs")
        jobs = await client.get("/api/jobs")
        root = await client.get("/")
        script = await client.get("/assets/app.js")
        missing = await client.get("/assets/absent.js")

    assert specs.status_code == 200
    assert "fe-gba-portrait-standard" in specs.json()
    assert jobs.json() == []

    # The static mount serves the real built entry point, not a placeholder,
    # and it never shadows the API or the WebSocket route.
    assert root.status_code == 200
    assert root.text == index_html
    assert root.headers["content-type"].startswith("text/html")
    assert script.status_code == 200
    assert script.text == "export {};\n"
    assert missing.status_code == 404
    assert any(getattr(route, "name", None) == "web" for route in api.routes)
    assert api.url_path_for("job_events", job_id="job-1") == "/ws/jobs/job-1"


async def test_serve_reports_a_clear_failure_when_web_assets_are_absent(
    serve_env: Path,
    captured_uvicorn: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(static_module, "web_dir", lambda: None)

    assert main(["serve"]) == 0

    api = captured_uvicorn["api"]
    transport = httpx.ASGITransport(app=api)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        root = await client.get("/")
        specs = await client.get("/api/specs")

    assert root.status_code == 503
    assert "npm run -w @laqieer/fecreator-web build" in root.text
    assert specs.status_code == 200
    assert not any(getattr(route, "name", None) == "web" for route in api.routes)


def test_serve_refuses_a_non_loopback_host(
    serve_env: Path,
    captured_uvicorn: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FECREATOR_HOST", "0.0.0.0")

    assert main(["serve"]) == 2
    assert captured_uvicorn == {}
    assert "0.0.0.0" in capsys.readouterr().err


def test_serve_reports_a_missing_data_root(
    captured_uvicorn: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("FECREATOR_DATA_ROOT", raising=False)

    assert main(["serve"]) == 2
    assert captured_uvicorn == {}
    assert "FECREATOR_DATA_ROOT" in capsys.readouterr().err


def test_serve_rejects_unknown_arguments(
    serve_env: Path,
    captured_uvicorn: dict[str, Any],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["serve", "--host", "0.0.0.0"])

    assert raised.value.code == 2
    assert captured_uvicorn == {}


def test_module_entry_point_runs_the_cli() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "fecreator", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.startswith("fecreator ")
