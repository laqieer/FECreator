from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from fecreator.app import AppError, FeCreatorApp, InvalidStateError, SpecNotFoundError
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fecreator")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-assets")
    sub.add_parser("list-specs")
    sub.add_parser("list-providers")

    # Validate a local package (trusted CLI path)
    validate = sub.add_parser("validate")
    validate.add_argument("--spec", required=True)
    validate.add_argument("--path", required=True)

    # Source planning / submission
    plan = sub.add_parser("plan-sources")
    plan.add_argument("job_id")

    submit = sub.add_parser("submit-sources")
    submit.add_argument("job_id")
    submit.add_argument("--from", dest="sources_dir", required=True, metavar="DIR")

    # Generation / build / inspect
    generate = sub.add_parser("generate")
    generate.add_argument("job_id")

    build_cmd = sub.add_parser("build")
    build_cmd.add_argument("job_id")

    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("job_id")

    # Approval
    approve_cmd = sub.add_parser("approve")
    approve_cmd.add_argument("job_id")
    approve_cmd.add_argument("--stage", required=True)
    approve_cmd.add_argument("--actor", required=True)

    reject_cmd = sub.add_parser("reject")
    reject_cmd.add_argument("job_id")
    reject_cmd.add_argument("--stage", required=True)
    reject_cmd.add_argument("--actor", required=True)
    reject_cmd.add_argument("--reason", required=True)

    # Job sub-commands
    job = sub.add_parser("job")
    job_sub = job.add_subparsers(dest="job_command", required=True)
    create = job_sub.add_parser("create")
    create.add_argument("--manifest", required=True)
    status = job_sub.add_parser("status")
    status.add_argument("job_id")
    cancel_cmd = job_sub.add_parser("cancel")
    cancel_cmd.add_argument("job_id")
    resume_cmd = job_sub.add_parser("resume")
    resume_cmd.add_argument("job_id")

    # Serve
    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=None)

    return parser


def _emit_error(code: str, message: str, err: TextIO | None = None) -> None:
    """Write a structured error to stderr (never to stdout)."""
    out = err if err is not None else sys.stderr
    json.dump({"error": code, "message": message}, out)
    out.write("\n")


def run(
    app: FeCreatorApp,
    argv: list[str],
    out: TextIO,
    err: TextIO | None = None,
) -> int:
    try:
        return _dispatch(app, argv, out, err)
    except InvalidStateError as exc:
        _emit_error("INVALID_STATE", str(exc), err)
        return 3
    except FileNotFoundError:
        _emit_error("NOT_FOUND", "resource not found", err)
        return 4
    except SpecNotFoundError as exc:
        _emit_error(exc.code, str(exc), err)
        return 4
    except AppError as exc:
        _emit_error(exc.code, str(exc), err)
        return 2
    except Exception:
        _emit_error("INTERNAL_ERROR", "an internal error occurred", err)
        return 5


def _dispatch(app: FeCreatorApp, argv: list[str], out: TextIO, err: TextIO | None) -> int:
    args = build_parser().parse_args(argv)

    def emit(obj: Any) -> None:
        json.dump(obj, out)

    if args.command == "list-assets":
        emit(app.list_assets())
    elif args.command == "list-specs":
        emit(app.list_specs())
    elif args.command == "list-providers":
        emit(app.list_providers())
    elif args.command == "validate":
        diags = app.validate(args.spec, Path(args.path))
        emit([d.model_dump(mode="json") for d in diags])
        return 2 if has_errors(diags) else 0
    elif args.command == "plan-sources":
        emit(app.plan_sources(args.job_id).model_dump(mode="json"))
    elif args.command == "submit-sources":
        emit(app.submit_sources(args.job_id, Path(args.sources_dir)).model_dump(mode="json"))
    elif args.command == "generate":
        emit(app.generate(args.job_id).model_dump(mode="json"))
    elif args.command == "build":
        emit(app.build(args.job_id).model_dump(mode="json"))
    elif args.command == "inspect":
        emit(app.inspect(args.job_id))
    elif args.command == "approve":
        emit(app.approve(args.job_id, args.stage, args.actor).model_dump(mode="json"))
    elif args.command == "reject":
        emit(app.reject(args.job_id, args.stage, args.actor, args.reason).model_dump(mode="json"))
    elif args.command == "job":
        if args.job_command == "create":
            manifest = Manifest.model_validate_json(Path(args.manifest).read_text())
            emit(app.create_job(manifest).model_dump(mode="json"))
        elif args.job_command == "status":
            emit(app.get_job(args.job_id).model_dump(mode="json"))
        elif args.job_command == "cancel":
            emit(app.cancel(args.job_id).model_dump(mode="json"))
        elif args.job_command == "resume":
            emit(app.resume(args.job_id).model_dump(mode="json"))
    elif args.command == "serve":
        import uvicorn

        from fecreator.interfaces.http_api import create_api

        host = args.host
        if host not in ("127.0.0.1", "localhost", "::1"):
            _emit_error(
                "UNSAFE_HOST",
                f"serve refuses to bind to {host!r}: only loopback is permitted in v1",
                err,
            )
            return 2
        port = args.port if args.port is not None else app._settings.port
        uvicorn.run(create_api(app), host=host, port=port)
    return 0
