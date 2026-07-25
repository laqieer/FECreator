from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import DiagData, Diagnostic, error
from fecreator.contracts.manifest import Manifest
from fecreator.core.paths import PathEscapeError, normalize_storage_id
from fecreator.core.registry import UnknownIdError
from fecreator.interfaces.static import mount_static
from fecreator.interfaces.websocket import register_ws
from fecreator.jobs.model import Job
from fecreator.reporting.sanitize import JsonObject, as_object, sanitize_json


class ExpectedHttpError(Exception):
    def __init__(self, status_code: int, diagnostics: Sequence[Diagnostic]) -> None:
        super().__init__("expected http error")
        self.status_code = status_code
        self.diagnostics = tuple(diagnostics)


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_id: str
    package_dir: str

    @field_validator("spec_id", "package_dir", mode="after")
    @classmethod
    def _validate_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be a non-empty string")
        return normalized


def _diagnostics_payload(diagnostics: Sequence[Diagnostic]) -> list[JsonObject]:
    return [
        as_object(sanitize_json(diagnostic.model_dump(mode="json"), error_cls=ValueError))
        for diagnostic in diagnostics
    ]


def _diagnostic_response(status_code: int, diagnostics: Sequence[Diagnostic]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=_diagnostics_payload(diagnostics))


def _validation_error_data(error_count: int) -> DiagData:
    return {"error_count": error_count}


def create_api(app: FeCreatorApp) -> FastAPI:
    api = FastAPI(
        title="FECreator",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    router = APIRouter(prefix="/api")

    @api.exception_handler(ExpectedHttpError)
    async def handle_expected_http_error(_request: Request, exc: ExpectedHttpError) -> JSONResponse:
        return _diagnostic_response(exc.status_code, exc.diagnostics)

    @api.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _diagnostic_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                error(
                    "INVALID_REQUEST",
                    "request failed validation",
                    where=request.url.path.lstrip("/"),
                    data=_validation_error_data(len(exc.errors())),
                )
            ],
        )

    @router.get("/assets")
    def list_assets() -> list[str]:
        return app.list_assets()

    @router.get("/specs")
    def list_specs() -> list[str]:
        return app.list_specs()

    @router.get("/providers")
    def list_providers() -> list[str]:
        return app.list_providers()

    @router.post("/jobs", status_code=status.HTTP_201_CREATED)
    def create_job(manifest: Manifest) -> Job:
        return app.create_job(manifest)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> Job:
        try:
            return app.get_job(normalize_storage_id(job_id, field_name="job_id"))
        except (FileNotFoundError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("UNKNOWN_JOB", "job not found", where=job_id)],
            ) from exc

    @router.post("/validate", response_model=list[Diagnostic])
    def validate(request: ValidateRequest) -> list[JsonObject]:
        try:
            diagnostics = app.validate(request.spec_id, Path(request.package_dir))
        except UnknownIdError as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("UNKNOWN_SPEC", "unknown target spec", where=str(exc.args[0]))],
            ) from exc
        return _diagnostics_payload(diagnostics)

    api.include_router(router)
    register_ws(api, app)
    mount_static(api)
    return api
