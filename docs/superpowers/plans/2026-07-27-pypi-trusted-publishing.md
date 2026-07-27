# PyPI Trusted Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `fecreator` to PyPI through GitHub Actions OIDC without
storing a PyPI token.

**Architecture:** A read-only build job validates the selected tag and creates
the wheel/sdist, then uploads them as a GitHub Actions artifact. A separate
`pypi` environment job receives only `id-token: write`, downloads those exact
files, and publishes them with the immutable PyPA action
`ba38be9e461d3875417946c167d0b5f3d385a247`.

**Tech Stack:** Python 3.12, Node.js 22, Hatchling, Twine, GitHub Actions OIDC,
PyPI Trusted Publishing, PyPA `gh-action-pypi-publish`.

## Global Constraints

- Never store a PyPI username, password, API token, or publishing credential.
- Use PyPI project `fecreator`, GitHub owner `laqieer`, repository `FECreator`,
  workflow `publish.yml`, and environment `pypi`.
- Build web assets before the Python distribution.
- Keep build and publish jobs separate; only the publish job gets
  `id-token: write`.
- Publish only an existing semantic tag whose version exactly matches both
  `pyproject.toml` and `src/fecreator/__init__.py`.
- Do not skip existing files or overwrite a published version.
- Do not create a GitHub Release.
- Keep `v0.1.0` immutable and publish it through manual workflow dispatch.
- Push every commit immediately and monitor CI asynchronously.

---

### Task 1: Validate release tags independently of package imports

**Files:**
- Create: `scripts/validate_release_tag.py`
- Create: `tests/test_release_tag.py`

**Interfaces:**
- Produces:
  `validate_release_tag(tag: str, pyproject: Path, package_init: Path) -> str`.
- CLI exits zero and prints the version for a valid tag; invalid input exits
  nonzero with no credential or absolute-path output.

- [ ] **Step 1: Write failing release-tag tests**

```python
from pathlib import Path

import pytest

from scripts.validate_release_tag import validate_release_tag


def _files(tmp_path: Path, project_version: str, package_version: str) -> tuple[Path, Path]:
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text(
        f'[project]\nname = "fecreator"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    package_init.write_text(
        f'__version__ = "{package_version}"\n',
        encoding="utf-8",
    )
    return pyproject, package_init


def test_validate_release_tag_returns_matching_version(tmp_path: Path) -> None:
    pyproject, package_init = _files(tmp_path, "0.1.0", "0.1.0")

    assert validate_release_tag("v0.1.0", pyproject, package_init) == "0.1.0"


@pytest.mark.parametrize(
    ("tag", "project_version", "package_version"),
    [
        ("0.1.0", "0.1.0", "0.1.0"),
        ("v01.0.0", "1.0.0", "1.0.0"),
        ("v0.1", "0.1.0", "0.1.0"),
        ("v0.1.1", "0.1.0", "0.1.0"),
        ("v0.1.0", "0.1.0", "0.1.1"),
    ],
)
def test_validate_release_tag_rejects_invalid_or_mismatched_versions(
    tmp_path: Path,
    tag: str,
    project_version: str,
    package_version: str,
) -> None:
    pyproject, package_init = _files(
        tmp_path,
        project_version,
        package_version,
    )

    with pytest.raises(ValueError):
        validate_release_tag(tag, pyproject, package_init)
```

- [ ] **Step 2: Run the focused tests and verify the import fails**

Run:

```powershell
C:\Projects\FECreator\.venv\Scripts\python.exe -m pytest -q tests/test_release_tag.py
```

Expected: collection fails because `scripts.validate_release_tag` does not
exist.

- [ ] **Step 3: Implement strict tag and version parsing**

```python
from __future__ import annotations

import argparse
import ast
import re
import tomllib
from pathlib import Path

SEMVER_TAG = re.compile(
    r"^v(?P<version>(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))$"
)


def _package_version(package_init: Path) -> str:
    tree = ast.parse(package_init.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ValueError("package __version__ is missing or invalid")


def validate_release_tag(tag: str, pyproject: Path, package_init: Path) -> str:
    match = SEMVER_TAG.fullmatch(tag)
    if match is None:
        raise ValueError("release tag must match v<major>.<minor>.<patch>")
    tag_version = match.group("version")
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project_version = project["project"]["version"]
    package_version = _package_version(package_init)
    if not isinstance(project_version, str):
        raise ValueError("project version must be a string")
    if tag_version != project_version or tag_version != package_version:
        raise ValueError("release tag and project versions do not match")
    return tag_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument(
        "--package-init",
        type=Path,
        default=Path("src/fecreator/__init__.py"),
    )
    args = parser.parse_args(argv)
    print(
        validate_release_tag(
            args.tag,
            args.pyproject,
            args.package_init,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused and repository checks**

Run:

```powershell
C:\Projects\FECreator\.venv\Scripts\python.exe -m pytest -q tests/test_release_tag.py
C:\Projects\FECreator\.venv\Scripts\ruff.exe check scripts/validate_release_tag.py tests/test_release_tag.py
C:\Projects\FECreator\.venv\Scripts\ruff.exe format --check scripts/validate_release_tag.py tests/test_release_tag.py
C:\Projects\FECreator\.venv\Scripts\python.exe -m mypy scripts/validate_release_tag.py
```

Expected: all commands exit zero.

- [ ] **Step 5: Commit and push**

```powershell
git add scripts/validate_release_tag.py tests/test_release_tag.py
git commit -m "feat: validate Python release tags" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 2: Add the separated OIDC build and publish workflow

**Files:**
- Create: `.github/workflows/publish.yml`
- Create: `tests/test_pypi_publish_workflow.py`
- Create: `docs/pypi-publishing.md`
- Modify: `README.md`

**Interfaces:**
- Tag push and manual dispatch select an immutable `RELEASE_TAG`.
- Build job produces artifact `python-distributions`.
- Publish job consumes only that artifact and obtains an OIDC token through
  environment `pypi`.

- [ ] **Step 1: Write failing workflow-policy tests**

```python
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/publish.yml")


def _workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_publish_workflow_uses_separate_oidc_job() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    build = jobs["build"]
    publish = jobs["publish"]

    assert build["permissions"] == {"contents": "read"}
    assert publish["needs"] == ["build"]
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }


def test_publish_action_is_immutable_and_has_no_token() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "pypa/gh-action-pypi-publish@"
        "ba38be9e461d3875417946c167d0b5f3d385a247"
    ) in text
    assert "PYPI_API_TOKEN" not in text
    assert "password:" not in text
    assert "skip-existing" not in text
    assert "softprops/action-gh-release" not in text


def test_publish_workflow_builds_web_before_python_distribution() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["build"]["steps"]
    commands = [
        step["run"]
        for step in steps
        if isinstance(step, dict) and "run" in step
    ]

    assert commands.index("npm run -w @laqieer/fecreator-web build") < commands.index(
        "python -m build"
    )
    assert "python -m twine check dist/*" in commands
```

- [ ] **Step 2: Run tests and verify the workflow is missing**

Run:

```powershell
C:\Projects\FECreator\.venv\Scripts\python.exe -m pytest -q tests/test_pypi_publish_workflow.py
```

Expected: tests fail because `.github/workflows/publish.yml` does not exist.

- [ ] **Step 3: Add the trusted-publishing workflow**

```yaml
name: Publish Python package

on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch:
    inputs:
      tag:
        description: Existing semantic version tag to publish
        required: true
        type: string

permissions:
  contents: read

env:
  RELEASE_TAG: >-
    ${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}

jobs:
  build:
    name: Build distributions
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ env.RELEASE_TAG }}
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: npm ci
      - run: python -m pip install --upgrade build twine
      - run: python scripts/validate_release_tag.py --tag "$RELEASE_TAG"
      - run: npm run -w @laqieer/fecreator-web build
      - run: python -m build
      - run: python -m twine check dist/*
      - uses: actions/upload-artifact@v4
        with:
          name: python-distributions
          path: dist/
          if-no-files-found: error
          retention-days: 7

  publish:
    name: Publish distributions to PyPI
    needs:
      - build
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/fecreator
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: python-distributions
          path: dist/
      - uses: pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247
```

- [ ] **Step 4: Document pending-publisher setup and run checks**

`docs/pypi-publishing.md` must list these exact pending-publisher values:

```text
Project: fecreator
Owner: laqieer
Repository: FECreator
Workflow: publish.yml
Environment: pypi
```

It also documents:

```powershell
gh workflow run publish.yml --ref main -f tag=v0.1.0
```

Run:

```powershell
C:\Projects\FECreator\.venv\Scripts\python.exe -m pytest -q tests/test_release_tag.py tests/test_pypi_publish_workflow.py tests/test_ci_pages_workflow.py
C:\Projects\FECreator\.venv\Scripts\ruff.exe check .
C:\Projects\FECreator\.venv\Scripts\ruff.exe format --check .
C:\Projects\FECreator\.venv\Scripts\python.exe -m mypy src scripts/validate_release_tag.py
```

Expected: all commands exit zero.

- [ ] **Step 5: Commit and push**

```powershell
git add .github/workflows/publish.yml tests/test_pypi_publish_workflow.py docs/pypi-publishing.md README.md
git commit -m "ci: publish Python packages with OIDC" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 3: Configure the trust boundary and publish v0.1.0

**Files:**
- No repository file changes unless a real workflow failure requires a tested
  correction.

**Interfaces:**
- GitHub environment `pypi`.
- PyPI pending publisher matching the exact repository identity.
- Manual workflow run publishing tag `v0.1.0`.

- [ ] **Step 1: Create the GitHub environment**

Run:

```powershell
gh api --method PUT repos/laqieer/FECreator/environments/pypi
```

Expected: the API returns environment `pypi`.

- [ ] **Step 2: Configure the pending publisher in the authenticated PyPI UI**

Open:

```text
https://pypi.org/manage/account/publishing/
```

Enter:

```text
Project: fecreator
Owner: laqieer
Repository: FECreator
Workflow: publish.yml
Environment: pypi
```

No credential is entered into the repository, GitHub Secrets, chat, or assistant
tools.

- [ ] **Step 3: Dispatch the existing v0.1.0 tag**

Run:

```powershell
gh workflow run publish.yml --repo laqieer/FECreator --ref main -f tag=v0.1.0
```

Monitor the run asynchronously. If authentication fails, compare the workflow,
environment, owner, repository, and project fields exactly; do not fall back to
an API token.

- [ ] **Step 4: Verify PyPI publication**

Run:

```powershell
python -m pip index versions fecreator
python -m pip download --no-deps --dest .pytest-pypi-probe fecreator==0.1.0
```

Expected: version `0.1.0` is listed and the wheel or sdist downloads.

Delete only `.pytest-pypi-probe` after verification.

- [ ] **Step 5: Record completion**

Confirm:

```text
https://pypi.org/project/fecreator/0.1.0/
```

No GitHub Release is created.
