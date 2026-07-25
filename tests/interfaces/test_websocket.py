from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _client(data_root: Path) -> TestClient:
    return TestClient(create_api(FeCreatorApp(Settings(data_root=data_root))))


def test_ws_streams_event_snapshot(tmp_path: Path) -> None:
    app = FeCreatorApp(Settings(data_root=tmp_path))
    job = app.create_job(_manifest())
    client = TestClient(create_api(app))

    with client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        message = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()

    assert message["job_id"] == job.id
    assert any(event["kind"] == "created" for event in message["events"])
    assert exc_info.value.code == 1000


def test_ws_rejects_unknown_job_deterministically(tmp_path: Path) -> None:
    client = _client(tmp_path)

    with (
        client.websocket_connect("/ws/jobs/missing-job") as ws,
        pytest.raises(WebSocketDisconnect) as exc_info,
    ):
        ws.receive_json()

    assert exc_info.value.code == 1008
