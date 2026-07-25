# Interfaces Task 11 Report

Status: done

Summary:
- Added `GET /ws/jobs/{id}` as a thin websocket surface over `FeCreatorApp.get_job()` and `FeCreatorApp.events()`.
- The websocket sends one `{ job_id, events }` JSON snapshot, then closes.
- Unknown or invalid job ids now close deterministically with policy-violation code 1008.
- Wired the websocket registration into `create_api()` before the static mount.

Verification:
- `pytest tests/app/test_app.py tests/interfaces/test_http_api.py tests/interfaces/test_websocket.py -v`
- `ruff check src\fecreator\interfaces\http_api.py src\fecreator\interfaces\websocket.py tests\interfaces\test_websocket.py`
- `ruff format --check src\fecreator\interfaces\http_api.py src\fecreator\interfaces\websocket.py tests\interfaces\test_websocket.py`
- `mypy src\fecreator\interfaces`

Concerns:
- The test run emits a pre-existing `StarletteDeprecationWarning` about `httpx2` in FastAPI's test client. It does not affect this change.
