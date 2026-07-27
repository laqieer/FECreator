import contextlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

import pytest

import fecreator

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NPM_REGISTRY = "https://registry.npmjs.org/"
FRONTEND_ENTRYPOINT = Path("src/fecreator/_web/index.html")
SDIST_ROOT = f"fecreator-{fecreator.__version__}"

# The essential packaging ignore: the generated bundle is never committed, so
# only the force-include tables may put it into a distribution.
CLONE_GITIGNORE = "src/fecreator/_web/\n"
# A linked worktree lives under an ignored directory, so its own project root
# matches a `.gitignore` pattern.  Hatchling then drops every VCS pattern.
WORKTREE_GITIGNORE = "src/fecreator/_web/\n.worktrees/\n"


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


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _link_workspace(project_dir: Path) -> None:
    """Reproduce the npm workspace link that aliases `web/` under `node_modules`.

    A build walk that descends into the link sees the linked directory first and
    can then drop the real `web/` sources through loop detection.  Creating a
    directory symlink needs a privilege Windows does not always grant, so the
    link is best effort; the assertions stay meaningful without it.
    """
    link = project_dir / "node_modules" / "@laqieer" / "fecreator-web"
    link.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError, NotImplementedError):
        link.symlink_to(project_dir / "web", target_is_directory=True)


def _stage_project(project_dir: Path, gitignore: str) -> None:
    """Stage a self-contained copy of the distribution inputs.

    The frontend bundle is synthesized rather than copied so packaging is
    proved with or without a real `npm run build` in the working tree, and so
    the assertions below describe packaging behaviour instead of bundle
    contents.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "pyproject.toml", project_dir / "pyproject.toml")
    shutil.copy2(REPO_ROOT / "README.md", project_dir / "README.md")
    shutil.copy2(REPO_ROOT / "hatch_build.py", project_dir / "hatch_build.py")
    shutil.copytree(
        REPO_ROOT / "src",
        project_dir / "src",
        ignore=shutil.ignore_patterns("__pycache__", "_web"),
    )
    (project_dir / ".gitignore").write_text(gitignore, encoding="utf-8", newline="\n")

    # Vendored and generated trees that must never reach a distribution, staged
    # so the assertions below prove packaging exclusions rather than an empty
    # working tree.
    for junk in (
        project_dir / "node_modules" / "left-pad" / "index.js",
        project_dir / "web" / "node_modules" / "vite" / "index.js",
        project_dir / "web" / "dist-demo" / "index.html",
    ):
        junk.parent.mkdir(parents=True, exist_ok=True)
        junk.write_text("// staged junk\n", encoding="utf-8", newline="\n")

    for kept in (
        project_dir / "web" / "package.json",
        project_dir / "web" / "src" / "main.tsx",
    ):
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text("{}\n", encoding="utf-8", newline="\n")

    _link_workspace(project_dir)

    web = project_dir / "src" / "fecreator" / "_web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text(
        '<!doctype html><script src="/assets/app.js"></script>\n',
        encoding="utf-8",
        newline="\n",
    )
    (web / "assets" / "app.js").write_text("export {};\n", encoding="utf-8", newline="\n")


def _build_distributions(project_dir: Path) -> tuple[Path, Path]:
    """Build the sdist and the wheel straight from the source tree.

    Both targets are named explicitly so the wheel is built from the project
    directory rather than from the unpacked sdist; a wheel built from an sdist
    lands in a temporary path and would silently hide project-root defects.
    """
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--no-isolation"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    dist = project_dir / "dist"
    return next(dist.glob("*.tar.gz")), next(dist.glob("*.whl"))


def _sdist_names(sdist: Path) -> list[str]:
    with tarfile.open(sdist) as archive:
        return archive.getnames()


def _wheel_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


@pytest.fixture(scope="module")
def clone_distributions() -> Iterator[tuple[Path, Path]]:
    """Build from a path that no `.gitignore` pattern matches (a normal clone)."""
    probe = Path(tempfile.mkdtemp(prefix=".pytest-package-probe-", dir=REPO_ROOT))
    try:
        project_dir = probe / "checkout"
        _stage_project(project_dir, CLONE_GITIGNORE)
        yield _build_distributions(project_dir)
    finally:
        shutil.rmtree(probe, ignore_errors=True)


def test_clone_build_includes_the_frontend_entrypoint_exactly_once(
    clone_distributions: tuple[Path, Path],
) -> None:
    sdist, wheel = clone_distributions

    assert [n for n in _sdist_names(sdist) if n.endswith("src/fecreator/_web/index.html")] == [
        f"{SDIST_ROOT}/src/fecreator/_web/index.html"
    ]
    assert [n for n in _wheel_names(wheel) if n.endswith("_web/index.html")] == [
        "fecreator/_web/index.html"
    ]


def test_linked_worktree_build_includes_the_frontend_entrypoint_exactly_once() -> None:
    """Build from a project root that its own `.gitignore` matches.

    Hatchling discards every VCS ignore pattern when the project root itself is
    ignored, which is exactly what a linked worktree under `.worktrees/` looks
    like.  The generated bundle must then still reach the archives once, from
    the force-include tables only.
    """
    probe = Path(tempfile.mkdtemp(prefix=".pytest-package-probe-", dir=REPO_ROOT))
    try:
        project_dir = probe / ".worktrees" / "checkout"
        _stage_project(project_dir, WORKTREE_GITIGNORE)
        sdist, wheel = _build_distributions(project_dir)

        assert [n for n in _sdist_names(sdist) if n.endswith("src/fecreator/_web/index.html")] == [
            f"{SDIST_ROOT}/src/fecreator/_web/index.html"
        ]
        assert [n for n in _wheel_names(wheel) if n.endswith("_web/index.html")] == [
            "fecreator/_web/index.html"
        ]
        assert not [n for n in _sdist_names(sdist) if "node_modules/" in n]
        assert not [n for n in _sdist_names(sdist) if "dist-demo/" in n]
    finally:
        shutil.rmtree(probe, ignore_errors=True)


def test_built_archives_never_carry_the_javascript_workspace(
    clone_distributions: tuple[Path, Path],
) -> None:
    sdist, wheel = clone_distributions

    assert not [n for n in _sdist_names(sdist) if "node_modules/" in n]
    assert not [n for n in _sdist_names(sdist) if "dist-demo/" in n]
    assert not [n for n in _wheel_names(wheel) if "node_modules/" in n]


def test_sdist_keeps_the_frontend_sources_next_to_the_workspace_link(
    clone_distributions: tuple[Path, Path],
) -> None:
    sdist, _ = clone_distributions
    names = _sdist_names(sdist)

    assert f"{SDIST_ROOT}/web/src/main.tsx" in names
    assert f"{SDIST_ROOT}/web/package.json" in names


def test_installed_wheel_exposes_the_packaged_frontend(
    clone_distributions: tuple[Path, Path], tmp_path: Path
) -> None:
    _, wheel = clone_distributions
    venv_dir = tmp_path / "target"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    install = subprocess.run(
        [
            str(_venv_python(venv_dir)),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--disable-pip-version-check",
            str(wheel),
        ],
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    smoke = subprocess.run(
        [
            str(_venv_python(venv_dir)),
            "-c",
            (
                "import json, fecreator\n"
                "from importlib import resources\n"
                "from pathlib import Path\n"
                "root = Path(str(resources.files('fecreator')))\n"
                "index = root / '_web' / 'index.html'\n"
                "print(json.dumps({\n"
                "    'version': fecreator.__version__,\n"
                "    'index': index.is_file(),\n"
                "    'assets': (root / '_web' / 'assets').is_dir(),\n"
                "    'inside': str(root) in str(index.resolve()),\n"
                "}))\n"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr

    report = json.loads(smoke.stdout.strip().splitlines()[-1])
    assert report == {
        "version": fecreator.__version__,
        "index": True,
        "assets": True,
        "inside": True,
    }


def test_generated_frontend_bundle_is_never_committed() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "src/fecreator/_web/" in ignored
