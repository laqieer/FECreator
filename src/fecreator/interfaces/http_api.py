from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fecreator.app import AppError, FeCreatorApp, InvalidStateError, SpecNotFoundError
from fecreator.contracts.manifest import Manifest
from fecreator.interfaces.static import web_dir


class _ApproveRequest(BaseModel):
    stage: str
    actor: str


class _RejectRequest(BaseModel):
    stage: str
    actor: str
    reason: str


class _ValidateJobRequest(BaseModel):
    spec_id: str


def _map_error(exc: Exception) -> HTTPException:
    """Map domain errors to appropriate HTTP responses with no path/trace leakage."""
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail="not found")
    if isinstance(exc, InvalidStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SpecNotFoundError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, AppError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="internal error")


def create_api(app: FeCreatorApp) -> FastAPI:
    api = FastAPI(title="FECreator")

    @api.get("/api/assets")
    def list_assets() -> list[str]:
        return app.list_assets()

    @api.get("/api/specs")
    def list_specs() -> list[str]:
        return app.list_specs()

    @api.get("/api/providers")
    def list_providers() -> list[str]:
        return app.list_providers()

    @api.post("/api/jobs")
    def create_job(manifest: Manifest) -> dict[str, object]:
        return app.create_job(manifest).model_dump(mode="json")

    @api.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return app.get_job(job_id).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/plan-sources")
    def plan_sources(job_id: str) -> dict[str, object]:
        try:
            return app.plan_sources(job_id).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/generate")
    def generate(job_id: str) -> dict[str, object]:
        try:
            return app.generate(job_id).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/build")
    def build(job_id: str) -> dict[str, object]:
        try:
            return app.build(job_id).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.get("/api/jobs/{job_id}/inspect")
    def inspect(job_id: str) -> dict[str, object]:
        try:
            return app.inspect(job_id)
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/validate")
    def validate_job(job_id: str, req: _ValidateJobRequest) -> list[dict[str, object]]:
        try:
            diags = app.validate_job(job_id, req.spec_id)
            return [d.model_dump(mode="json") for d in diags]
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/approve")
    def approve(job_id: str, req: _ApproveRequest) -> dict[str, object]:
        try:
            return app.approve(job_id, req.stage, req.actor).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/reject")
    def reject(job_id: str, req: _RejectRequest) -> dict[str, object]:
        try:
            return app.reject(job_id, req.stage, req.actor, req.reason).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    @api.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, object]:
        try:
            return app.cancel(job_id).model_dump(mode="json")
        except Exception as exc:
            raise _map_error(exc) from exc

    from fecreator.interfaces.websocket import register_ws

    register_ws(api, app)
    mount_static(api)
    return api


def mount_static(api: FastAPI) -> None:
    directory = web_dir()
    if directory is not None:
        api.mount("/", StaticFiles(directory=str(directory), html=True), name="web")
