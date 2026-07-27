"""Policy tests for the PyPI trusted-publishing workflow.

The publish workflow is the only place where an OIDC identity can mint a PyPI
token, so its trust boundary is pinned here: an unprivileged build job produces
immutable distributions, and a separate environment-gated job publishes them
without ever building code or holding a long-lived credential.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"

PINNED_PUBLISH_ACTION = "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247"
ARTIFACT_NAME = "python-distributions"


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def _triggers() -> dict[str, Any]:
    workflow = _workflow()
    # PyYAML parses the bare ``on`` key as the boolean ``True`` (YAML 1.1).
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _job(name: str) -> dict[str, Any]:
    job = _workflow()["jobs"][name]
    assert isinstance(job, dict)
    return job


def _steps(name: str) -> list[dict[str, Any]]:
    return [step for step in _job(name)["steps"] if isinstance(step, dict)]


def _commands(name: str) -> list[str]:
    return [str(step["run"]) for step in _steps(name) if "run" in step]


def _uses(name: str) -> list[str]:
    return [str(step["uses"]) for step in _steps(name) if "uses" in step]


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_publish_workflow_exists_and_is_not_reusable() -> None:
    assert WORKFLOW.is_file()
    triggers = _triggers()
    assert "workflow_call" not in triggers


def test_publish_workflow_triggers_on_semantic_tags_and_manual_dispatch() -> None:
    triggers = _triggers()

    assert triggers["push"]["tags"] == ["v*.*.*"]
    assert "branches" not in triggers["push"]

    dispatch_input = triggers["workflow_dispatch"]["inputs"]["tag"]
    assert dispatch_input["required"] is True
    assert dispatch_input["type"] == "string"


def test_release_tag_prefers_the_dispatch_input_over_the_pushed_ref() -> None:
    release_tag = _workflow()["env"]["RELEASE_TAG"]

    assert "github.event_name == 'workflow_dispatch'" in release_tag
    assert "inputs.tag" in release_tag
    assert "github.ref_name" in release_tag


def test_workflow_default_permissions_are_read_only() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}


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


def test_only_the_publish_job_can_mint_an_oidc_token() -> None:
    jobs = _workflow()["jobs"]
    minters = {name for name, job in jobs.items() if (job.get("permissions") or {}).get("id-token")}

    assert minters == {"publish"}
    assert "id-token" not in _workflow()["permissions"]


def test_publish_job_runs_on_ubuntu_and_targets_the_project_page() -> None:
    publish = _job("publish")

    assert publish["runs-on"] == "ubuntu-latest"
    assert publish["environment"]["url"] == "https://pypi.org/p/fecreator"


def test_build_job_checks_out_the_immutable_release_tag() -> None:
    checkout = next(
        step
        for step in _steps("build")
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )

    assert checkout["with"]["ref"] == "${{ env.RELEASE_TAG }}"


def test_build_job_validates_the_tag_before_building_anything() -> None:
    commands = _commands("build")
    validate = next(
        index for index, command in enumerate(commands) if "validate_release_tag.py" in command
    )

    assert '--tag "$RELEASE_TAG"' in commands[validate]
    assert validate < commands.index("npm run -w @laqieer/fecreator-web build")
    assert validate < commands.index("python -m build")


def test_publish_workflow_builds_web_before_python_distribution() -> None:
    commands = _commands("build")

    assert commands.index("npm run -w @laqieer/fecreator-web build") < commands.index(
        "python -m build"
    )
    assert "python -m twine check dist/*" in commands


def test_build_job_installs_node_and_python_toolchains() -> None:
    uses = _uses("build")

    assert any(u.startswith("actions/setup-node@") for u in uses)
    assert any(u.startswith("actions/setup-python@") for u in uses)
    assert "npm ci" in _commands("build")


def test_build_job_uploads_the_distributions_and_fails_when_empty() -> None:
    upload = next(
        step
        for step in _steps("build")
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )

    assert upload["with"]["name"] == ARTIFACT_NAME
    assert upload["with"]["path"] == "dist/"
    assert upload["with"]["if-no-files-found"] == "error"


def test_publish_job_consumes_only_the_build_artifact() -> None:
    steps = _steps("publish")
    download = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/download-artifact@")
    )

    assert download["with"]["name"] == ARTIFACT_NAME
    assert download["with"]["path"] == "dist/"
    assert [str(step.get("uses", "")) for step in steps] == [
        download["uses"],
        PINNED_PUBLISH_ACTION,
    ]


def test_publish_job_never_checks_out_or_builds_code() -> None:
    steps = _steps("publish")

    assert not any("run" in step for step in steps)
    assert not any(str(step.get("uses", "")).startswith("actions/checkout@") for step in steps)


def test_publish_action_is_immutable_and_has_no_token() -> None:
    text = _text()

    assert PINNED_PUBLISH_ACTION in text
    assert "PYPI_API_TOKEN" not in text
    assert "password:" not in text
    assert "skip-existing" not in text
    assert "softprops/action-gh-release" not in text


def test_publish_workflow_carries_no_credentials_release_or_rom_steps() -> None:
    lowered = _text().lower()

    for forbidden in (
        "secrets.",
        "api_token",
        "api-token",
        "username:",
        "gh release",
        "create-release",
    ):
        assert forbidden not in lowered

    assert re.search(r"\brom\b", lowered) is None


def test_publish_workflow_file_ends_with_a_newline() -> None:
    assert WORKFLOW.read_bytes()[-1:] == b"\n"


DOCS = REPO_ROOT / "docs" / "pypi-publishing.md"


def test_docs_list_the_exact_pending_publisher_fields() -> None:
    text = DOCS.read_text(encoding="utf-8")

    for field in (
        "Project: fecreator",
        "Owner: laqieer",
        "Repository: FECreator",
        "Workflow: publish.yml",
        "Environment: pypi",
    ):
        assert field in text


def test_docs_show_the_manual_dispatch_command_and_pin() -> None:
    text = DOCS.read_text(encoding="utf-8")

    assert "gh workflow run publish.yml --ref main -f tag=v0.1.0" in text
    assert PINNED_PUBLISH_ACTION in text


def test_readme_links_the_publishing_guide() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "[`docs/pypi-publishing.md`](docs/pypi-publishing.md)" in readme
