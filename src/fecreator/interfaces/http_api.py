from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest
from fecreator.interfaces.static import web_dir


class ValidateRequest(BaseModel):
    spec_id: str
    package_dir: str


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
        except (FileNotFoundError, KeyError) as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @api.post("/api/validate")
    def validate(request: ValidateRequest) -> list[dict[str, object]]:
        diags = app.validate(request.spec_id, Path(request.package_dir))
        return [d.model_dump(mode="json") for d in diags]

    from fecreator.interfaces.websocket import register_ws

    register_ws(api, app)
    mount_static(api)
    return api


def mount_static(api: FastAPI) -> None:
    directory = web_dir()
    if directory is not None:
        api.mount("/", StaticFiles(directory=str(directory), html=True), name="web")
