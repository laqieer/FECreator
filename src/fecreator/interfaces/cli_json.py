from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TextIO, TypeAlias, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError

from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import Diagnostic, error, has_errors
from fecreator.contracts.manifest import Manifest
from fecreator.core.registry import UnknownIdError
from fecreator.reporting.sanitize import JsonValue, sanitize_json

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
    try:
        job = app.get_job(args.job_id)
    except FileNotFoundError as exc:
        raise ExpectedCliError(error("UNKNOWN_JOB", "job not found", where=args.job_id)) from exc
    return 0, _model_payload(job)


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
