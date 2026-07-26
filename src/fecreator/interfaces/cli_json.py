from __future__ import annotations

import argparse
import base64
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TextIO, TypeAlias, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError

from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import DiagData, Diagnostic, error, has_errors
from fecreator.contracts.manifest import Manifest
from fecreator.core.paths import PathEscapeError, normalize_storage_id
from fecreator.core.registry import UnknownIdError
from fecreator.jobs.approvals import ApprovalError
from fecreator.jobs.model import Job
from fecreator.jobs.service import InvalidTransitionError
from fecreator.references.store import ReferencePackCorruptionError
from fecreator.reporting.sanitize import JsonValue, sanitize_json, sanitize_text

CommandHandler: TypeAlias = Callable[[FeCreatorApp, argparse.Namespace], tuple[int, JsonValue]]
ParserT = TypeVar("ParserT", bound=argparse.ArgumentParser)
NamespaceT = TypeVar("NamespaceT")


class ExpectedCliError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class JsonCliArgumentParser(argparse.ArgumentParser):
    @overload
    def parse_args(
        self,
        args: Iterable[str] | None = None,
        namespace: None = None,
    ) -> argparse.Namespace: ...

    @overload
    def parse_args(
        self,
        args: Iterable[str] | None,
        namespace: NamespaceT,
    ) -> NamespaceT: ...

    @overload
    def parse_args(self, *, namespace: NamespaceT) -> NamespaceT: ...

    def parse_args(
        self,
        args: Iterable[str] | None = None,
        namespace: object = None,
    ) -> object:
        argv = list(args) if args is not None else None
        if argv is not None:
            self._reject_unknown_long_options(argv)
        return super().parse_args(args=argv, namespace=namespace)

    def _reject_unknown_long_options(self, argv: list[str]) -> None:
        known = self._known_long_options()
        for token in argv:
            if token == "--":
                break
            option, _, _value = token.partition("=")
            if option.startswith("--") and option != "--" and option not in known:
                self.error(f"unrecognized arguments: {option}")

    def _known_long_options(self) -> set[str]:
        known: set[str] = set()
        stack: list[argparse.ArgumentParser] = [self]
        while stack:
            parser = stack.pop()
            for action in parser._actions:
                known.update(
                    option
                    for option in action.option_strings
                    if option.startswith("--") and option != "--"
                )
                if isinstance(action, argparse._SubParsersAction):
                    stack.extend(cast(list[argparse.ArgumentParser], action.choices.values()))
        return known


def _write_json(out: TextIO, payload: JsonValue) -> None:
    safe_payload = sanitize_json(payload, error_cls=ValueError)
    out.write(json.dumps(safe_payload, sort_keys=True, separators=(",", ":")))


def _model_payload(model: BaseModel) -> JsonValue:
    return cast(JsonValue, model.model_dump(mode="json"))


def _diagnostics_payload(diagnostics: list[Diagnostic]) -> JsonValue:
    return [_model_payload(diagnostic) for diagnostic in diagnostics]


def _models_payload(models: Iterable[BaseModel]) -> JsonValue:
    return [_model_payload(model) for model in models]


def _detail_data(exc: Exception) -> DiagData | None:
    detail = str(exc).strip()
    if not detail:
        return None
    return {"detail": sanitize_text(detail)}


def _load_known_job(app: FeCreatorApp, job_id: str) -> Job:
    try:
        normalized = normalize_storage_id(job_id, field_name="job_id")
        return app.get_job(normalized)
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(error("UNKNOWN_JOB", "job not found", where=job_id)) from exc


def _run_list_assets(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_assets())


def _run_list_specs(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_specs())


def _run_list_providers(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_providers())


def _run_validate(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    try:
        diagnostics = app.validate(args.spec_id, Path(args.package_dir))
    except UnknownIdError as exc:
        raise ExpectedCliError(
            error("UNKNOWN_SPEC", "unknown target spec", where=cast(str, exc.args[0]))
        ) from exc
    return (2 if has_errors(diagnostics) else 0), _diagnostics_payload(diagnostics)


def _read_manifest(path: Path) -> Manifest:
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ExpectedCliError(
            error("MANIFEST_NOT_FOUND", "manifest file not found", where=str(path))
        ) from exc
    try:
        return Manifest.model_validate_json(payload)
    except ValidationError as exc:
        raise ExpectedCliError(
            error(
                "INVALID_MANIFEST",
                "manifest failed validation",
                where=str(path),
                data={"error_count": len(exc.errors())},
            )
        ) from exc


def _run_job_create(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, _model_payload(app.create_job(_read_manifest(Path(args.manifest_path))))


def _run_job_status(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, _model_payload(_load_known_job(app, args.job_id))


def _run_job_list(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, _models_payload(app.list_jobs())


def _run_job_candidate(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _model_payload(app.get_job_candidate(job.id))
    except FileNotFoundError as exc:
        raise ExpectedCliError(
            error("CANDIDATE_NOT_FOUND", "job candidate not found", where=job.id)
        ) from exc


def _run_job_approvals(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    return 0, _models_payload(app.list_approval_decisions(job.id))


def _run_job_plan_sources(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _model_payload(app.plan_job_sources(job.id))
    except FileNotFoundError as exc:
        if job.manifest.character_ref_pack is not None:
            raise ExpectedCliError(
                error(
                    "UNKNOWN_REFERENCE_PACK",
                    "reference pack not found",
                    where=job.manifest.character_ref_pack,
                )
            ) from exc
        raise ExpectedCliError(
            error("PLAN_SOURCES_FAILED", "could not plan sources", where=job.id)
        ) from exc
    except ReferencePackCorruptionError as exc:
        raise ExpectedCliError(
            error(
                "CORRUPT_REFERENCE_PACK",
                "reference pack is corrupt",
                where=job.manifest.character_ref_pack,
            )
        ) from exc
    except (InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "PLAN_SOURCES_FAILED",
                "could not plan sources",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_validate(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        diagnostics = app.validate_job(job.id)
    except (OSError, PathEscapeError, UnknownIdError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "VALIDATE_JOB_FAILED",
                "could not validate job",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc
    return (2 if has_errors(diagnostics) else 0), _diagnostics_payload(diagnostics)


def _file_payload(path: str, content: bytes) -> JsonValue:
    return {
        "content_base64": base64.b64encode(content).decode("ascii"),
        "path": path,
    }


def _run_job_artifact(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _file_payload(
            args.relative_path,
            app.read_job_artifact(job.id, args.relative_path),
        )
    except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "READ_ARTIFACT_FAILED",
                "could not read job artifact",
                where=args.relative_path,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_report(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, app.get_job_report(job.id)
    except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "READ_REPORT_FAILED",
                "could not read job report",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_bundle(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _models_payload(app.list_bundle_entries(job.id))
    except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "LIST_BUNDLE_FAILED",
                "could not list job bundle",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_bundle_file(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _file_payload(
            args.relative_path,
            app.read_bundle_file(job.id, args.relative_path),
        )
    except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "READ_BUNDLE_FILE_FAILED",
                "could not read bundle file",
                where=args.relative_path,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_approve(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _model_payload(app.approve_review(job.id, args.actor))
    except (ApprovalError, InvalidTransitionError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "APPROVE_REVIEW_FAILED",
                "could not approve candidate review",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_reject(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _model_payload(app.reject_review(job.id, args.actor, args.reason))
    except (ApprovalError, InvalidTransitionError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "REJECT_REVIEW_FAILED",
                "could not reject candidate review",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_finalize(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        result = app.finalize_job(job.id)
    except (ApprovalError, InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "FINALIZE_JOB_FAILED",
                "could not finalize job",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc
    return (0 if result.ok else 2), _model_payload(result)


def _run_job_retry(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _model_payload(app.retry_job(job.id, args.actor))
    except (ApprovalError, InvalidTransitionError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "RETRY_JOB_FAILED",
                "could not retry job",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_job_cancel(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        return 0, _model_payload(app.cancel(job.id))
    except InvalidTransitionError as exc:
        raise ExpectedCliError(
            error(
                "CANCEL_JOB_FAILED",
                "could not cancel job",
                where=job.id,
                data=_detail_data(exc),
            )
        ) from exc


def _run_plan_sources(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        plan = app.plan_sources(job.id, Path(args.out_dir))
    except FileNotFoundError as exc:
        if job.manifest.character_ref_pack is not None:
            raise ExpectedCliError(
                error(
                    "UNKNOWN_REFERENCE_PACK",
                    "reference pack not found",
                    where=job.manifest.character_ref_pack,
                )
            ) from exc
        raise ExpectedCliError(
            error(
                "PLAN_SOURCES_FAILED",
                "could not plan sources",
                where=args.out_dir,
                data=_detail_data(exc),
            )
        ) from exc
    except ReferencePackCorruptionError as exc:
        raise ExpectedCliError(
            error(
                "CORRUPT_REFERENCE_PACK",
                "reference pack is corrupt",
                where=job.manifest.character_ref_pack,
            )
        ) from exc
    except (InvalidTransitionError, OSError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "PLAN_SOURCES_FAILED",
                "could not plan sources",
                where=args.out_dir,
                data=_detail_data(exc),
            )
        ) from exc
    return 0, _model_payload(plan)


def _run_submit_sources(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        submitted = app.submit_sources(job.id, Path(args.sources_dir))
    except (
        FileExistsError,
        FileNotFoundError,
        InvalidTransitionError,
        OSError,
        PathEscapeError,
        ValueError,
    ) as exc:
        raise ExpectedCliError(
            error(
                "SUBMIT_SOURCES_FAILED",
                "could not submit sources",
                where=args.sources_dir,
                data=_detail_data(exc),
            )
        ) from exc
    return 0, _model_payload(submitted)


def _run_build(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    job = _load_known_job(app, args.job_id)
    try:
        result = app.build(job.id)
    except ReferencePackCorruptionError as exc:
        raise ExpectedCliError(
            error(
                "CORRUPT_REFERENCE_PACK",
                "reference pack is corrupt",
                where=job.manifest.character_ref_pack,
            )
        ) from exc
    except (InvalidTransitionError, OSError, PathEscapeError, UnknownIdError, ValueError) as exc:
        raise ExpectedCliError(
            error(
                "BUILD_ASSET_FAILED",
                "could not build asset",
                where=args.job_id,
                data=_detail_data(exc),
            )
        ) from exc
    return (0 if result.ok else 2), _model_payload(result)


def _run_reference_list(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_reference_packs())


def _run_reference_history(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    try:
        pack_id = normalize_storage_id(args.pack_id, field_name="pack_id")
        return 0, _models_payload(app.list_reference_history(pack_id))
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error("UNKNOWN_REFERENCE_PACK", "reference pack not found", where=args.pack_id)
        ) from exc


def _run_lineage_get(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    try:
        asset_id = normalize_storage_id(args.asset_id, field_name="asset_id")
        return 0, _model_payload(app.get_lineage(asset_id))
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error("UNKNOWN_LINEAGE", "lineage asset not found", where=args.asset_id)
        ) from exc


def _run_lineage_ancestors(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    try:
        asset_id = normalize_storage_id(args.asset_id, field_name="asset_id")
        return 0, _models_payload(app.list_lineage_ancestors(asset_id))
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error("UNKNOWN_LINEAGE", "lineage asset not found", where=args.asset_id)
        ) from exc


def _run_lineage_children(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    try:
        asset_id = normalize_storage_id(args.asset_id, field_name="asset_id")
        return 0, _models_payload(app.list_lineage_children(asset_id))
    except (FileNotFoundError, PathEscapeError, ValueError) as exc:
        raise ExpectedCliError(
            error("UNKNOWN_LINEAGE", "lineage asset not found", where=args.asset_id)
        ) from exc


def _add_list_parser(
    subparsers: argparse._SubParsersAction[ParserT],
    name: str,
    *,
    handler: CommandHandler,
) -> None:
    parser = subparsers.add_parser(name, allow_abbrev=False)
    parser.set_defaults(handler=handler)


def _add_validate_parser(
    subparsers: argparse._SubParsersAction[ParserT],
) -> None:
    parser = subparsers.add_parser("validate", allow_abbrev=False)
    parser.add_argument("--spec", dest="spec_id", required=True)
    parser.add_argument("--path", dest="package_dir", required=True)
    parser.set_defaults(handler=_run_validate)


def _add_job_parser(subparsers: argparse._SubParsersAction[ParserT]) -> None:
    parser = subparsers.add_parser("job", allow_abbrev=False)
    job_subparsers = parser.add_subparsers(dest="job_command", required=True)

    create_parser = job_subparsers.add_parser("create", allow_abbrev=False)
    create_parser.add_argument("--manifest", dest="manifest_path", required=True)
    create_parser.set_defaults(handler=_run_job_create)

    status_parser = job_subparsers.add_parser("status", allow_abbrev=False)
    status_parser.add_argument("job_id")
    status_parser.set_defaults(handler=_run_job_status)

    list_parser = job_subparsers.add_parser("list", allow_abbrev=False)
    list_parser.set_defaults(handler=_run_job_list)

    candidate_parser = job_subparsers.add_parser("candidate", allow_abbrev=False)
    candidate_parser.add_argument("job_id")
    candidate_parser.set_defaults(handler=_run_job_candidate)

    approvals_parser = job_subparsers.add_parser("approvals", allow_abbrev=False)
    approvals_parser.add_argument("job_id")
    approvals_parser.set_defaults(handler=_run_job_approvals)

    plan_sources_parser = job_subparsers.add_parser("plan-sources", allow_abbrev=False)
    plan_sources_parser.add_argument("job_id")
    plan_sources_parser.set_defaults(handler=_run_job_plan_sources)

    validate_parser = job_subparsers.add_parser("validate", allow_abbrev=False)
    validate_parser.add_argument("job_id")
    validate_parser.set_defaults(handler=_run_job_validate)

    artifact_parser = job_subparsers.add_parser("artifact", allow_abbrev=False)
    artifact_parser.add_argument("job_id")
    artifact_parser.add_argument("relative_path")
    artifact_parser.set_defaults(handler=_run_job_artifact)

    report_parser = job_subparsers.add_parser("report", allow_abbrev=False)
    report_parser.add_argument("job_id")
    report_parser.set_defaults(handler=_run_job_report)

    bundle_parser = job_subparsers.add_parser("bundle", allow_abbrev=False)
    bundle_parser.add_argument("job_id")
    bundle_parser.set_defaults(handler=_run_job_bundle)

    bundle_file_parser = job_subparsers.add_parser("bundle-file", allow_abbrev=False)
    bundle_file_parser.add_argument("job_id")
    bundle_file_parser.add_argument("relative_path")
    bundle_file_parser.set_defaults(handler=_run_job_bundle_file)

    approve_parser = job_subparsers.add_parser("approve", allow_abbrev=False)
    approve_parser.add_argument("job_id")
    approve_parser.add_argument("--actor", required=True)
    approve_parser.set_defaults(handler=_run_job_approve)

    reject_parser = job_subparsers.add_parser("reject", allow_abbrev=False)
    reject_parser.add_argument("job_id")
    reject_parser.add_argument("--actor", required=True)
    reject_parser.add_argument("--reason", required=True)
    reject_parser.set_defaults(handler=_run_job_reject)

    finalize_parser = job_subparsers.add_parser("finalize", allow_abbrev=False)
    finalize_parser.add_argument("job_id")
    finalize_parser.set_defaults(handler=_run_job_finalize)

    retry_parser = job_subparsers.add_parser("retry", allow_abbrev=False)
    retry_parser.add_argument("job_id")
    retry_parser.add_argument("--actor", required=True)
    retry_parser.set_defaults(handler=_run_job_retry)

    cancel_parser = job_subparsers.add_parser("cancel", allow_abbrev=False)
    cancel_parser.add_argument("job_id")
    cancel_parser.set_defaults(handler=_run_job_cancel)


def _add_references_parser(subparsers: argparse._SubParsersAction[ParserT]) -> None:
    parser = subparsers.add_parser("references", allow_abbrev=False)
    reference_subparsers = parser.add_subparsers(dest="reference_command", required=True)

    list_parser = reference_subparsers.add_parser("list", allow_abbrev=False)
    list_parser.set_defaults(handler=_run_reference_list)

    history_parser = reference_subparsers.add_parser("history", allow_abbrev=False)
    history_parser.add_argument("pack_id")
    history_parser.set_defaults(handler=_run_reference_history)


def _add_lineage_parser(subparsers: argparse._SubParsersAction[ParserT]) -> None:
    parser = subparsers.add_parser("lineage", allow_abbrev=False)
    lineage_subparsers = parser.add_subparsers(dest="lineage_command", required=True)

    get_parser = lineage_subparsers.add_parser("get", allow_abbrev=False)
    get_parser.add_argument("asset_id")
    get_parser.set_defaults(handler=_run_lineage_get)

    ancestors_parser = lineage_subparsers.add_parser("ancestors", allow_abbrev=False)
    ancestors_parser.add_argument("asset_id")
    ancestors_parser.set_defaults(handler=_run_lineage_ancestors)

    children_parser = lineage_subparsers.add_parser("children", allow_abbrev=False)
    children_parser.add_argument("asset_id")
    children_parser.set_defaults(handler=_run_lineage_children)


def _add_plan_sources_parser(subparsers: argparse._SubParsersAction[ParserT]) -> None:
    parser = subparsers.add_parser("plan-sources", allow_abbrev=False)
    parser.add_argument("--job", dest="job_id", required=True)
    parser.add_argument("--out", dest="out_dir", required=True)
    parser.set_defaults(handler=_run_plan_sources)


def _add_submit_sources_parser(subparsers: argparse._SubParsersAction[ParserT]) -> None:
    parser = subparsers.add_parser("submit-sources", allow_abbrev=False)
    parser.add_argument("--job", dest="job_id", required=True)
    parser.add_argument("--sources", dest="sources_dir", required=True)
    parser.set_defaults(handler=_run_submit_sources)


def _add_build_parser(subparsers: argparse._SubParsersAction[ParserT]) -> None:
    parser = subparsers.add_parser("build", allow_abbrev=False)
    parser.add_argument("--job", dest="job_id", required=True)
    parser.set_defaults(handler=_run_build)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonCliArgumentParser(prog="fecreator", allow_abbrev=False)
    parser.add_argument(
        "--version",
        action="version",
        help="show program's version number and exit",
        version=f"fecreator {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_list_parser(subparsers, "list-assets", handler=_run_list_assets)
    _add_list_parser(subparsers, "list-specs", handler=_run_list_specs)
    _add_list_parser(subparsers, "list-providers", handler=_run_list_providers)
    _add_validate_parser(subparsers)
    _add_job_parser(subparsers)
    _add_references_parser(subparsers)
    _add_lineage_parser(subparsers)
    _add_plan_sources_parser(subparsers)
    _add_submit_sources_parser(subparsers)
    _add_build_parser(subparsers)
    return parser


def dispatch(app: FeCreatorApp, args: argparse.Namespace, out: TextIO) -> int:
    handler = cast(CommandHandler, args.handler)
    try:
        exit_code, payload = handler(app, args)
    except ExpectedCliError as exc:
        _write_json(out, _diagnostics_payload([exc.diagnostic]))
        return 2
    _write_json(out, payload)
    return exit_code


def run(app: FeCreatorApp, argv: list[str], out: TextIO) -> int:
    return dispatch(app, build_parser().parse_args(argv), out)
