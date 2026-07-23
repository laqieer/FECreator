from __future__ import annotations

import argparse

from fecreator import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fecreator")
    parser.add_argument("--version", action="version", version=f"fecreator {__version__}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
