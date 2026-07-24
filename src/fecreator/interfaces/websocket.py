from __future__ import annotations

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from fecreator.app import FeCreatorApp
from fecreator.jobs.model import JobState

_TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED})
_POLL_INTERVAL = 0.5  # seconds between event polls
_MAX_WAIT = 300.0  # hard timeout in seconds


def register_ws(api: FastAPI, app: FeCreatorApp) -> None:
    @api.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        # Verify job exists before accepting the connection
        try:
            app.get_job(job_id)
        except FileNotFoundError:
            await websocket.close(code=4004, reason="job not found")
            return

        await websocket.accept()
        sent_up_to = 0
        elapsed = 0.0

        try:
            while elapsed < _MAX_WAIT:
                events = app.events(job_id)
                new_events = [e.model_dump(mode="json") for e in events[sent_up_to:]]

                if new_events:
                    await websocket.send_json(
                        {
                            "job_id": job_id,
                            "events": new_events,
                            "seq_start": sent_up_to,
                        }
                    )
                    sent_up_to += len(new_events)

                job = app.get_job(job_id)
                if job.state in _TERMINAL_STATES:
                    # Flush any remaining events, then close cleanly
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
                    await websocket.close()
                    return

                await asyncio.sleep(_POLL_INTERVAL)
                elapsed += _POLL_INTERVAL

            # Timeout: close cleanly
            await websocket.close()
        except WebSocketDisconnect:
            pass
