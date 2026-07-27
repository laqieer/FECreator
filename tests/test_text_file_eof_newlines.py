from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_FILES = [
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "publish.yml",
    REPO_ROOT / "docs" / "pypi-publishing.md",
    REPO_ROOT / "pyproject.toml",
    REPO_ROOT / "web" / ".env.demo",
    REPO_ROOT / "web" / "package.json",
    REPO_ROOT / "web" / "vite.config.ts",
    REPO_ROOT / "web" / "src" / "vite-env.d.ts",
]


def test_workflow_and_config_text_files_end_with_newlines() -> None:
    missing = [path.as_posix() for path in TEXT_FILES if path.read_bytes()[-1:] != b"\n"]
    assert missing == []
