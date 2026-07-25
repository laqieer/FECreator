from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO, TypeAlias, cast

from pydantic import BaseModel

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import Diagnostic, has_errors
from fecreator.contracts.manifest import Manifest
from fecreator.reporting.sanitize import JsonValue, sanitize_json

CommandHandler: TypeAlias = Callable[[FeCreatorApp, argparse.Namespace], tuple[int, JsonValue]]


def _write_json(out: TextIO, payload: JsonValue) -> None:
    safe_payload = sanitize_json(payload, error_cls=ValueError)
    out.write(json.dumps(safe_payload, sort_keys=True, separators=(",", ":")))


def _model_payload(model: BaseModel) -> JsonValue:
    return cast(JsonValue, model.model_dump(mode="json"))


def _diagnostics_payload(diagnostics: list[Diagnostic]) -> JsonValue:
    return [_model_payload(diagnostic) for diagnostic in diagnostics]


def _run_list_assets(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_assets())


def _run_list_specs(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_specs())


def _run_list_providers(app: FeCreatorApp, _args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, cast(JsonValue, app.list_providers())


def _run_validate(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    diagnostics = app.validate(args.spec_id, Path(args.package_dir))
    return (2 if has_errors(diagnostics) else 0), _diagnostics_payload(diagnostics)


def _read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def _run_job_create(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, _model_payload(app.create_job(_read_manifest(Path(args.manifest_path))))


def _run_job_status(app: FeCreatorApp, args: argparse.Namespace) -> tuple[int, JsonValue]:
    return 0, _model_payload(app.get_job(args.job_id))


def _add_list_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    *,
    handler: CommandHandler,
) -> None:
    parser = subparsers.add_parser(name)
    parser.set_defaults(handler=handler)


def _add_validate_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("validate")
    parser.add_argument("--spec", dest="spec_id", required=True)
    parser.add_argument("--path", dest="package_dir", required=True)
    parser.set_defaults(handler=_run_validate)


def _add_job_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("job")
    job_subparsers = parser.add_subparsers(dest="job_command", required=True)

    create_parser = job_subparsers.add_parser("create")
    create_parser.add_argument("--manifest", dest="manifest_path", required=True)
    create_parser.set_defaults(handler=_run_job_create)

    status_parser = job_subparsers.add_parser("status")
    status_parser.add_argument("job_id")
    status_parser.set_defaults(handler=_run_job_status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fecreator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_list_parser(subparsers, "list-assets", handler=_run_list_assets)
    _add_list_parser(subparsers, "list-specs", handler=_run_list_specs)
    _add_list_parser(subparsers, "list-providers", handler=_run_list_providers)
    _add_validate_parser(subparsers)
    _add_job_parser(subparsers)
    return parser


def dispatch(app: FeCreatorApp, args: argparse.Namespace, out: TextIO) -> int:
    handler = cast(CommandHandler, args.handler)
    exit_code, payload = handler(app, args)
    _write_json(out, payload)
    return exit_code


def run(app: FeCreatorApp, argv: list[str], out: TextIO) -> int:
    return dispatch(app, build_parser().parse_args(argv), out)
