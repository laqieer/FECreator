"""Opt-in smoke check for a configured FEBuilder-compatible executable.

This is supplementary level-2 evidence (see ``docs/febuilder-interop.md``). It
runs only when ``FEBUILDER_CLI`` names an executable, it never needs a ROM, and
it never replaces the mandatory deterministic roundtrip. A nonzero exit from the
configured executable fails the test rather than being downgraded to a warning.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fecreator.interop.febuilder_cli import (
    CLI_ENV_VAR,
    febuilder_cli_from_env,
    run_febuilder_cli,
)
from tests.fixtures.gba import write_valid_package

pytestmark = pytest.mark.skipif(
    not os.environ.get(CLI_ENV_VAR, "").strip(),
    reason=f"{CLI_ENV_VAR} is not configured; the external CLI check is opt-in",
)


def test_configured_executable_accepts_a_canonical_package(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_valid_package(package)
    cli = febuilder_cli_from_env()
    assert cli is not None

    result = run_febuilder_cli(cli, "validate-asset", package, root=tmp_path)

    assert result.status == "passed", (
        f"configured febuilder cli rejected a canonical package "
        f"(exit_code={result.exit_code}): {result.stderr or result.stdout}"
    )
    assert result.exit_code == 0
