from fastapi.testclient import TestClient

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces.http_api import create_api


def test_ws_streams_event_snapshot(tmp_path):  # type: ignore[no-untyped-def]
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
    client = TestClient(create_api(app))
    with client.websocket_connect(f"/ws/jobs/{job.id}") as ws:
        message = ws.receive_json()
    assert message["job_id"] == job.id
    assert any(e["kind"] == "created" for e in message["events"])
