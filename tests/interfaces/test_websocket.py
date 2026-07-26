from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fecreator.app import FeCreatorApp
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api
from fecreator.jobs.candidates import CandidateStore
from fecreator.jobs.model import JobState
from fecreator.lineage.store import LineageStore


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


def test_ws_includes_review_events_persisted_by_http_actions(tmp_path: Path) -> None:
    app = FeCreatorApp(Settings(data_root=tmp_path))
    job = app.create_job(_manifest())
    candidate_id = f"{job.id}-candidate"
    LineageStore(tmp_path).add(
        LineageNode(
            asset_id=candidate_id,
            operation=Operation.CREATE_NEUTRAL,
            created_at="2026-07-26T00:00:00+00:00",
        )
    )
    CandidateStore(tmp_path).create(
        CandidateSnapshot(
            job_id=job.id,
            lineage_id=candidate_id,
            artifacts=(),
            created_at="2026-07-26T00:00:00+00:00",
        )
    )
    app._service.transition_path(
        job.id,
        (JobState.PLANNING, JobState.PROCESSING, JobState.WAITING_FOR_REVIEW),
    )
    client = TestClient(create_api(app))

    response = client.post(f"/api/jobs/{job.id}/approve", json={"actor": "reviewer"})
    with client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        snapshot = ws.receive_json()

    assert response.status_code == 200
    assert any(event["kind"] == "review_approved" for event in snapshot["events"])
