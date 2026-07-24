import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import fecreator

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NPM_REGISTRY = "https://registry.npmjs.org/"
FRONTEND_ENTRYPOINT = Path("src/fecreator/_web/index.html")


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


def test_package_lock_uses_public_npm_registry() -> None:
    lockfile = json.loads((REPO_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    offenders: list[str] = []

    for package_path, metadata in lockfile["packages"].items():
        resolved = metadata.get("resolved")
        if not resolved:
            continue
        if "://" not in resolved:
            continue

        parsed = urlparse(resolved)
        if f"{parsed.scheme}://{parsed.netloc}/" != PUBLIC_NPM_REGISTRY:
            label = package_path or "<root>"
            offenders.append(f"{label}: {resolved}")

    assert not offenders, (
        f"package-lock.json must only resolve packages from {PUBLIC_NPM_REGISTRY}\n"
        + "\n".join(offenders[:10])
    )


def test_build_fails_when_frontend_entrypoint_is_missing() -> None:
    project_dir = Path(tempfile.mkdtemp(prefix=".pytest-build-probe-", dir=REPO_ROOT))
    try:
        shutil.copy2(REPO_ROOT / "pyproject.toml", project_dir / "pyproject.toml")
        shutil.copy2(REPO_ROOT / "README.md", project_dir / "README.md")
        shutil.copytree(REPO_ROOT / "src", project_dir / "src")

        build_hook = REPO_ROOT / "hatch_build.py"
        if build_hook.exists():
            shutil.copy2(build_hook, project_dir / "hatch_build.py")

        frontend_entrypoint = project_dir / FRONTEND_ENTRYPOINT
        if frontend_entrypoint.exists():
            frontend_entrypoint.unlink()

        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr

        assert result.returncode != 0
        assert "src/fecreator/_web/index.html" in output
        assert "npm run -w @laqieer/fecreator-web build" in output
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)


def test_build_editable_succeeds_without_frontend_entrypoint() -> None:
    project_dir = Path(tempfile.mkdtemp(prefix=".pytest-editable-probe-", dir=REPO_ROOT))
    try:
        shutil.copy2(REPO_ROOT / "pyproject.toml", project_dir / "pyproject.toml")
        shutil.copy2(REPO_ROOT / "README.md", project_dir / "README.md")
        shutil.copytree(REPO_ROOT / "src", project_dir / "src")

        build_hook = REPO_ROOT / "hatch_build.py"
        if build_hook.exists():
            shutil.copy2(build_hook, project_dir / "hatch_build.py")

        web_dir = project_dir / "src" / "fecreator" / "_web"
        if web_dir.exists():
            shutil.rmtree(web_dir)

        venv_dir = project_dir / ".venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=True,
        )
        python_dir = "Scripts" if sys.platform == "win32" else "bin"
        python_name = "python.exe" if sys.platform == "win32" else "python"
        venv_python = venv_dir / python_dir / python_name

        result = subprocess.run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "-e",
                str(project_dir),
            ],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        assert web_dir.is_dir()
        assert not (web_dir / "index.html").exists()
        assert "Missing required frontend asset" not in output
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
