from __future__ import annotations

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from fecreator.app import FeCreatorApp
from fecreator.jobs.model import JobState

_TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED})
_POLL_INTERVAL = 0.5  # seconds between event polls
_MAX_WAIT = 300.0  # hard timeout in seconds
_WS_CODE_JOB_NOT_FOUND = 4004
_WS_CODE_JOB_ERROR = 4010


def register_ws(api: FastAPI, app: FeCreatorApp) -> None:
    @api.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        try:
            app.get_job(job_id)
        except FileNotFoundError:
            await websocket.close(code=_WS_CODE_JOB_NOT_FOUND, reason="job not found")
            return

        await websocket.accept()
        sent_up_to = 0
        elapsed = 0.0

        try:
            while elapsed < _MAX_WAIT:
                try:
                    events = app.events(job_id)
                    job = app.get_job(job_id)
                except (FileNotFoundError, Exception):
                    import contextlib

                    with contextlib.suppress(Exception):
                        await websocket.send_json({"job_id": job_id, "error": "job unavailable"})
                    await websocket.close(code=_WS_CODE_JOB_ERROR)
                    return

                new_events = [e.model_dump(mode="json") for e in events[sent_up_to:]]
                if new_events:
                    await websocket.send_json(
                        {"job_id": job_id, "events": new_events, "seq_start": sent_up_to}
                    )
                    sent_up_to += len(new_events)

                if job.state in _TERMINAL_STATES:
                    try:
                        final_events = app.events(job_id)
                        remaining = [e.model_dump(mode="json") for e in final_events[sent_up_to:]]
                        if remaining:
                            await websocket.send_json(
                                {
                                    "job_id": job_id,
                                    "events": remaining,
                                    "seq_start": sent_up_to,
                                }
                            )
                    except Exception:
                        pass
                    await websocket.close()
                    return

                await asyncio.sleep(_POLL_INTERVAL)
                elapsed += _POLL_INTERVAL

            await websocket.close()
        except WebSocketDisconnect:
            pass
