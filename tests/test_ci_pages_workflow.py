from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _deploy_job() -> dict:
    return _workflow()["jobs"]["deploy-pages"]


def test_deploy_pages_is_gated_to_main_pushes() -> None:
    condition = _deploy_job()["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition


def test_pull_requests_can_never_deploy() -> None:
    condition = _deploy_job()["if"]
    assert "pull_request" not in condition
    assert "github.event_name == 'push'" in condition


def test_deploy_pages_needs_all_build_and_test_jobs() -> None:
    assert set(_deploy_job()["needs"]) == {"python", "web", "package"}


def test_deploy_pages_builds_demo_and_uploads_the_web_bundle() -> None:
    steps = _deploy_job()["steps"]
    run_text = " ".join(step.get("run", "") for step in steps)
    assert "build:demo" in run_text
    upload = next(
        s for s in steps if s.get("uses", "").startswith("actions/upload-pages-artifact@")
    )
    assert upload["with"]["path"] == "src/fecreator/_web"


def test_deploy_pages_uses_official_pages_actions() -> None:
    uses = [step.get("uses", "") for step in _deploy_job()["steps"]]
    assert any(u.startswith("actions/configure-pages@") for u in uses)
    assert any(u.startswith("actions/upload-pages-artifact@") for u in uses)
    assert any(u.startswith("actions/deploy-pages@") for u in uses)


def test_deploy_pages_has_least_privilege_permissions() -> None:
    assert _deploy_job()["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }


def test_deploy_pages_targets_pages_environment_with_serial_concurrency() -> None:
    job = _deploy_job()
    assert job["environment"]["name"] == "github-pages"
    assert job["concurrency"]["group"] == "pages"
    assert job["concurrency"]["cancel-in-progress"] is False


def test_web_job_verifies_root_relative_assets() -> None:
    steps = _workflow()["jobs"]["web"]["steps"]
    run_text = " ".join(step.get("run", "") for step in steps)
    assert '"/assets/' in run_text
