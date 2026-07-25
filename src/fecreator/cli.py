from __future__ import annotations

import sys

from fecreator import __version__
from fecreator.app import FeCreatorApp
from fecreator.core.config import get_settings
from fecreator.interfaces import cli_json


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--version":
        print(f"fecreator {__version__}")
        return 0

    args = cli_json.build_parser().parse_args(argv)
    app = FeCreatorApp(get_settings())
    rc = cli_json.dispatch(app, args, sys.stdout)
    sys.stdout.write("\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
