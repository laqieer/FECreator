from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from fecreator.app import FeCreatorApp
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fecreator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-assets")
    sub.add_parser("list-specs")
    sub.add_parser("list-providers")
    validate = sub.add_parser("validate")
    validate.add_argument("--spec", required=True)
    validate.add_argument("--path", required=True)
    job = sub.add_parser("job")
    job_sub = job.add_subparsers(dest="job_command", required=True)
    create = job_sub.add_parser("create")
    create.add_argument("--manifest", required=True)
    status = job_sub.add_parser("status")
    status.add_argument("job_id")
    return parser


def run(app: FeCreatorApp, argv: list[str], out: TextIO) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-assets":
        json.dump(app.list_assets(), out)
    elif args.command == "list-specs":
        json.dump(app.list_specs(), out)
    elif args.command == "list-providers":
        json.dump(app.list_providers(), out)
    elif args.command == "validate":
        diags = app.validate(args.spec, Path(args.path))
        json.dump([d.model_dump(mode="json") for d in diags], out)
        return 2 if has_errors(diags) else 0
    elif args.command == "job" and args.job_command == "create":
        manifest = Manifest.model_validate_json(Path(args.manifest).read_text())
        json.dump(app.create_job(manifest).model_dump(mode="json"), out)
    elif args.command == "job" and args.job_command == "status":
        json.dump(app.get_job(args.job_id).model_dump(mode="json"), out)
    return 0
