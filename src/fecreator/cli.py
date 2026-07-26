from __future__ import annotations

import argparse
import ipaddress
import sys

from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings, get_settings
from fecreator.interfaces import cli_json

_SERVE_COMMAND = "serve"
_LOOPBACK_HOST_NAMES = frozenset({"localhost"})


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOST_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _serve_settings() -> Settings | None:
    try:
        return get_settings()
    except KeyError:
        sys.stderr.write("fecreator serve requires FECREATOR_DATA_ROOT to be set.\n")
        return None


def _serve(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="fecreator serve", allow_abbrev=False).parse_args(argv)
    settings = _serve_settings()
    if settings is None:
        return 2
    if not _is_loopback(settings.host):
        sys.stderr.write(
            f"fecreator serve binds loopback addresses only; {settings.host} is not loopback.\n"
        )
        return 2

    # Imported lazily so the JSON commands do not pay the HTTP stack import cost.
    import uvicorn

    from fecreator.interfaces.http_api import create_api

    uvicorn.run(
        create_api(FeCreatorApp(settings)),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--version":
        print(f"fecreator {__version__}")
        return 0
    if argv and argv[0] == _SERVE_COMMAND:
        return _serve(argv[1:])

    args = cli_json.build_parser().parse_args(argv)
    app = FeCreatorApp(get_settings())
    rc = cli_json.dispatch(app, args, sys.stdout)
    sys.stdout.write("\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
