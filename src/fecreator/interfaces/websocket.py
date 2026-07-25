from __future__ import annotations

from fastapi import FastAPI, WebSocket, status

from fecreator.app import FeCreatorApp
from fecreator.core.paths import PathEscapeError, normalize_storage_id

_UNKNOWN_JOB_CLOSE_CODE = status.WS_1008_POLICY_VIOLATION


def _job_events_payload(app: FeCreatorApp, job_id: str) -> dict[str, object]:
    normalized_job_id = normalize_storage_id(job_id, field_name="job_id")
    job = app.get_job(normalized_job_id)
    return {
        "job_id": job.id,
        "events": [event.model_dump(mode="json") for event in app.events(job.id)],
    }


def register_ws(api: FastAPI, app: FeCreatorApp) -> None:
    @api.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        try:
            payload = _job_events_payload(app, job_id)
        except (FileNotFoundError, PathEscapeError, ValueError):
            await websocket.close(code=_UNKNOWN_JOB_CLOSE_CODE)
            return

        await websocket.send_json(payload)
        await websocket.close()
