import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_dev_extra_explicitly_includes_pyyaml() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dev_dependencies = data["project"]["optional-dependencies"]["dev"]
    assert "pyyaml>=6,<7" in dev_dependencies
