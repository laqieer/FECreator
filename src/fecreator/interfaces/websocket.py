from __future__ import annotations

from fastapi import FastAPI, WebSocket

from fecreator.app import FeCreatorApp


def register_ws(api: FastAPI, app: FeCreatorApp) -> None:
    @api.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        events = [e.model_dump(mode="json") for e in app.events(job_id)]
        await websocket.send_json({"job_id": job_id, "events": events})
        await websocket.close()
