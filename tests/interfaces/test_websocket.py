from fastapi.testclient import TestClient

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api


def test_ws_streams_event_snapshot(tmp_path):  # type: ignore[no-untyped-def]
    """WS sends incremental event batches; initial create event must appear."""
    app = FeCreatorApp(Settings(data_root=tmp_path))
    job = app.create_job(
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            sources=(SourceSpec(kind="text", ref="hero"),),
        )
    )
    # Cancel immediately so the WS loop hits a terminal state quickly
    app.cancel(job.id)

    client = TestClient(create_api(app))
    all_events = []
    with client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        # Receive all messages until connection closes
        while True:
            try:
                msg = ws.receive_json()
                assert msg["job_id"] == job.id
                all_events.extend(msg["events"])
            except Exception:
                break

    kinds = {e["kind"] for e in all_events}
    assert "created" in kinds


def test_ws_rejects_unknown_job(tmp_path):  # type: ignore[no-untyped-def]
    """WS must close before accepting if job does not exist."""
    import pytest
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(create_api(FeCreatorApp(Settings(data_root=tmp_path))))
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/jobs/nonexistent") as ws:
        ws.receive_text()
