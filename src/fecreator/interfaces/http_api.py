from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated

from fastapi import APIRouter, FastAPI, File, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, field_validator

from fecreator.app import FeCreatorApp
from fecreator.assets.base import SourcePlan
from fecreator.contracts.diagnostics import DiagData, Diagnostic, error
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.contracts.result import JobResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.paths import PathEscapeError, normalize_storage_id
from fecreator.core.registry import UnknownIdError
from fecreator.interfaces.static import mount_static
from fecreator.interfaces.websocket import register_ws
from fecreator.jobs.approvals import ApprovalError, ApprovalRecord
from fecreator.jobs.model import Job
from fecreator.jobs.service import InvalidTransitionError
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackCorruptionError
from fecreator.reporting.bundle import BundleEntry
from fecreator.reporting.sanitize import JsonObject, as_object, sanitize_json, sanitize_text

MAX_UPLOAD_FILE_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_TOTAL_BYTES = 32 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 64 * 1024


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


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: str

    @field_validator("actor", mode="after")
    @classmethod
    def _validate_actor(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("actor must be a non-empty string")
        return normalized


class RejectRequest(ReviewRequest):
    reason: str

    @field_validator("reason", mode="after")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must be a non-empty string")
        return normalized


class UploadRejected(Exception):
    def __init__(self, code: str, message: str, where: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.where = where


def _diagnostics_payload(diagnostics: Sequence[Diagnostic]) -> list[JsonObject]:
    return [
        as_object(sanitize_json(diagnostic.model_dump(mode="json"), error_cls=ValueError))
        for diagnostic in diagnostics
    ]


def _diagnostic_response(status_code: int, diagnostics: Sequence[Diagnostic]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=_diagnostics_payload(diagnostics))


def _validation_error_data(error_count: int) -> DiagData:
    return {"error_count": error_count}


def _detail_data(exc: Exception) -> DiagData | None:
    detail = str(exc).strip()
    if not detail:
        return None
    return {"detail": sanitize_text(detail)}


def _known_job(app: FeCreatorApp, job_id: str) -> Job:
    try:
        return app.get_job(normalize_storage_id(job_id, field_name="job_id"))
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedHttpError(
            status.HTTP_404_NOT_FOUND,
            [error("UNKNOWN_JOB", "job not found", where=job_id)],
        ) from exc


def _normalize_upload_filename(filename: str | None) -> str:
    if filename is None or not filename or "/" in filename or "\\" in filename:
        raise UploadRejected("UPLOAD_UNSAFE_NAME", "upload filename is unsafe", "files")
    posix = PurePosixPath(filename)
    windows = PureWindowsPath(filename)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or len(posix.parts) != 1
        or len(windows.parts) != 1
        or len(filename) >= 2
        and filename[1] == ":"
    ):
        raise UploadRejected("UPLOAD_UNSAFE_NAME", "upload filename is unsafe", "files")
    try:
        return normalize_storage_id(filename, field_name="filename")
    except (PathEscapeError, ValueError) as exc:
        raise UploadRejected("UPLOAD_UNSAFE_NAME", "upload filename is unsafe", "files") from exc


async def _stream_uploads(files: list[UploadFile], destination: Path) -> None:
    names: set[str] = set()
    total_bytes = 0
    try:
        for upload in files:
            filename = _normalize_upload_filename(upload.filename)
            if filename.casefold() in names:
                raise UploadRejected(
                    "UPLOAD_DUPLICATE_NAME",
                    "upload filenames must be unique",
                    "files",
                )
            names.add(filename.casefold())
            received = 0
            try:
                with (destination / filename).open("xb") as staged:
                    while chunk := await upload.read(_UPLOAD_CHUNK_BYTES):
                        received += len(chunk)
                        total_bytes += len(chunk)
                        if received > MAX_UPLOAD_FILE_BYTES:
                            raise UploadRejected(
                                "UPLOAD_FILE_LIMIT",
                                "uploaded file exceeds the byte limit",
                                filename,
                            )
                        if total_bytes > MAX_UPLOAD_TOTAL_BYTES:
                            raise UploadRejected(
                                "UPLOAD_TOTAL_LIMIT",
                                "uploaded files exceed the total byte limit",
                                "files",
                            )
                        staged.write(chunk)
            finally:
                await upload.close()
    finally:
        for upload in files:
            await upload.close()


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

    @router.get("/jobs")
    def list_jobs() -> list[Job]:
        return app.list_jobs()

    @router.post("/jobs", status_code=status.HTTP_201_CREATED)
    def create_job(manifest: Manifest) -> Job:
        return app.create_job(manifest)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> Job:
        return _known_job(app, job_id)

    @router.get("/jobs/{job_id}/candidate")
    def get_job_candidate(job_id: str) -> CandidateSnapshot:
        job = _known_job(app, job_id)
        try:
            return app.get_job_candidate(job.id)
        except FileNotFoundError as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("CANDIDATE_NOT_FOUND", "job candidate not found", where=job.id)],
            ) from exc

    @router.get("/jobs/{job_id}/approvals")
    def list_approvals(job_id: str) -> list[ApprovalRecord]:
        return app.list_approval_decisions(_known_job(app, job_id).id)

    @router.post("/jobs/{job_id}/plan-sources")
    def plan_sources(job_id: str) -> SourcePlan:
        job = _known_job(app, job_id)
        try:
            return app.plan_job_sources(job.id)
        except FileNotFoundError as exc:
            code = (
                "UNKNOWN_REFERENCE_PACK"
                if job.manifest.character_ref_pack is not None
                else "PLAN_SOURCES_FAILED"
            )
            where = job.manifest.character_ref_pack or job.id
            message = (
                "reference pack not found"
                if job.manifest.character_ref_pack is not None
                else "could not plan sources"
            )
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error(code, message, where=where)],
            ) from exc
        except ReferencePackCorruptionError as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "CORRUPT_REFERENCE_PACK",
                        "reference pack is corrupt",
                        where=job.manifest.character_ref_pack,
                    )
                ],
            ) from exc
        except (InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "PLAN_SOURCES_FAILED",
                        "could not plan sources",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.post("/jobs/{job_id}/sources")
    async def submit_sources(
        job_id: str,
        files: Annotated[list[UploadFile], File(...)],
    ) -> Job:
        job = _known_job(app, job_id)
        try:
            with app.staged_source_upload(job.id) as source_dir:
                await _stream_uploads(files, source_dir)
                return app.submit_sources(job.id, source_dir)
        except UploadRejected as exc:
            raise ExpectedHttpError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                [error(exc.code, exc.message, where=exc.where)],
            ) from exc
        except (
            FileExistsError,
            FileNotFoundError,
            InvalidTransitionError,
            OSError,
            PathEscapeError,
            ValueError,
        ) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "SUBMIT_SOURCES_FAILED",
                        "could not submit sources",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.post("/jobs/{job_id}/validate", response_model=list[Diagnostic])
    def validate_job(job_id: str) -> list[JsonObject]:
        job = _known_job(app, job_id)
        try:
            return _diagnostics_payload(app.validate_job(job.id))
        except (OSError, PathEscapeError, UnknownIdError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "VALIDATE_JOB_FAILED",
                        "could not validate job",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.get("/jobs/{job_id}/artifacts/{relative_path:path}")
    def read_job_artifact(job_id: str, relative_path: str) -> Response:
        job = _known_job(app, job_id)
        try:
            content = app.read_job_artifact(job.id, relative_path)
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [
                    error(
                        "READ_ARTIFACT_FAILED",
                        "could not read job artifact",
                        where=relative_path,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc
        return Response(content=content, media_type="application/octet-stream")

    @router.get("/jobs/{job_id}/report")
    def get_job_report(job_id: str) -> JSONResponse:
        job = _known_job(app, job_id)
        try:
            return JSONResponse(content=app.get_job_report(job.id))
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [
                    error(
                        "READ_REPORT_FAILED",
                        "could not read job report",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.get("/jobs/{job_id}/bundle")
    def list_bundle_entries(job_id: str) -> list[BundleEntry]:
        job = _known_job(app, job_id)
        try:
            return app.list_bundle_entries(job.id)
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [
                    error(
                        "LIST_BUNDLE_FAILED",
                        "could not list job bundle",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.get("/jobs/{job_id}/bundle/{relative_path:path}")
    def read_bundle_file(job_id: str, relative_path: str) -> Response:
        job = _known_job(app, job_id)
        try:
            content = app.read_bundle_file(job.id, relative_path)
        except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [
                    error(
                        "READ_BUNDLE_FILE_FAILED",
                        "could not read bundle file",
                        where=relative_path,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc
        return Response(content=content, media_type="application/octet-stream")

    @router.post("/jobs/{job_id}/approve")
    def approve_review(job_id: str, request: ReviewRequest) -> ApprovalRecord:
        job = _known_job(app, job_id)
        try:
            return app.approve_review(job.id, request.actor)
        except (ApprovalError, InvalidTransitionError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "APPROVE_REVIEW_FAILED",
                        "could not approve candidate review",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.post("/jobs/{job_id}/reject")
    def reject_review(job_id: str, request: RejectRequest) -> ApprovalRecord:
        job = _known_job(app, job_id)
        try:
            return app.reject_review(job.id, request.actor, request.reason)
        except (ApprovalError, InvalidTransitionError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "REJECT_REVIEW_FAILED",
                        "could not reject candidate review",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.post("/jobs/{job_id}/finalize")
    def finalize_job(job_id: str) -> JobResult:
        job = _known_job(app, job_id)
        try:
            return app.finalize_job(job.id)
        except (ApprovalError, InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "FINALIZE_JOB_FAILED",
                        "could not finalize job",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.post("/jobs/{job_id}/retry")
    def retry_job(job_id: str, request: ReviewRequest) -> Job:
        job = _known_job(app, job_id)
        try:
            return app.retry_job(job.id, request.actor)
        except (ApprovalError, InvalidTransitionError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "RETRY_JOB_FAILED",
                        "could not retry job",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
            ) from exc

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> Job:
        job = _known_job(app, job_id)
        try:
            return app.cancel(job.id)
        except InvalidTransitionError as exc:
            raise ExpectedHttpError(
                status.HTTP_409_CONFLICT,
                [
                    error(
                        "CANCEL_JOB_FAILED",
                        "could not cancel job",
                        where=job.id,
                        data=_detail_data(exc),
                    )
                ],
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

    @router.get("/references")
    def list_reference_packs() -> list[str]:
        return app.list_reference_packs()

    @router.get("/references/{pack_id}/history")
    def list_reference_history(pack_id: str) -> list[ReferencePack]:
        try:
            normalized_pack_id = normalize_storage_id(pack_id, field_name="pack_id")
            return app.list_reference_history(normalized_pack_id)
        except (FileNotFoundError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("UNKNOWN_REFERENCE_PACK", "reference pack not found", where=pack_id)],
            ) from exc

    @router.get("/lineage/{asset_id}")
    def get_lineage(asset_id: str) -> LineageNode:
        try:
            normalized_asset_id = normalize_storage_id(asset_id, field_name="asset_id")
            return app.get_lineage(normalized_asset_id)
        except (FileNotFoundError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("UNKNOWN_LINEAGE", "lineage asset not found", where=asset_id)],
            ) from exc

    @router.get("/lineage/{asset_id}/ancestors")
    def list_lineage_ancestors(asset_id: str) -> list[LineageNode]:
        try:
            normalized_asset_id = normalize_storage_id(asset_id, field_name="asset_id")
            return app.list_lineage_ancestors(normalized_asset_id)
        except (FileNotFoundError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("UNKNOWN_LINEAGE", "lineage asset not found", where=asset_id)],
            ) from exc

    @router.get("/lineage/{asset_id}/children")
    def list_lineage_children(asset_id: str) -> list[LineageNode]:
        try:
            normalized_asset_id = normalize_storage_id(asset_id, field_name="asset_id")
            return app.list_lineage_children(normalized_asset_id)
        except (FileNotFoundError, PathEscapeError, ValueError) as exc:
            raise ExpectedHttpError(
                status.HTTP_404_NOT_FOUND,
                [error("UNKNOWN_LINEAGE", "lineage asset not found", where=asset_id)],
            ) from exc

    api.include_router(router)
    register_ws(api, app)
    mount_static(api)
    return api
