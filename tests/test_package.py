import subprocess
import sys

import fecreator


def test_version_is_semver() -> None:
    parts = fecreator.__version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def test_cli_version_matches_package() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "fecreator.cli", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert fecreator.__version__ in out.stdout
