from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers() -> dict:
    workflow = _workflow()
    # PyYAML parses the bare ``on`` key as the boolean ``True`` (YAML 1.1).
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _deploy_job() -> dict:
    return _workflow()["jobs"]["deploy-pages"]


def test_push_trigger_covers_all_branches_for_secret_scanning() -> None:
    triggers = _triggers()
    assert "push" in triggers
    push = triggers["push"]
    # An unfiltered push trigger runs the secret-scan job on every branch push.
    assert push is None or "branches" not in push
    if isinstance(push, dict) and "branches" in push:
        assert push["branches"] != ["main"]


def test_pull_request_trigger_is_present() -> None:
    assert "pull_request" in _triggers()


def test_widened_push_trigger_does_not_loosen_deploy_gate() -> None:
    condition = _deploy_job()["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition


def test_deploy_pages_is_gated_to_main_pushes() -> None:
    condition = _deploy_job()["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition


def test_pull_requests_can_never_deploy() -> None:
    condition = _deploy_job()["if"]
    assert "pull_request" not in condition
    assert "github.event_name == 'push'" in condition


def _job(name: str) -> dict:
    return _workflow()["jobs"][name]


def test_deploy_pages_needs_all_build_and_test_jobs() -> None:
    assert set(_deploy_job()["needs"]) == {"python", "web", "package", "secret-scan"}


def test_deploy_pages_needs_secret_scan_so_leaks_block_deploy() -> None:
    assert "secret-scan" in _deploy_job()["needs"]


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


PINNED_GGSHIELD_ACTION = "GitGuardian/ggshield-action@da20be06cafe5e8633dc24744efe1efe8d30f06b"


def _secret_scan_job() -> dict:
    return _job("secret-scan")


def _ggshield_step() -> dict:
    return next(
        s
        for s in _secret_scan_job()["steps"]
        if str(s.get("uses", "")).startswith("GitGuardian/ggshield-action@")
    )


def test_secret_scan_uses_pinned_official_action_sha() -> None:
    assert _ggshield_step()["uses"] == PINNED_GGSHIELD_ACTION


def test_secret_scan_has_least_privilege_permissions() -> None:
    assert _secret_scan_job()["permissions"] == {"contents": "read"}


def test_secret_scan_checks_out_full_history() -> None:
    checkout = next(
        s
        for s in _secret_scan_job()["steps"]
        if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0


def test_secret_scan_passes_api_key_from_actions_secrets() -> None:
    env = _ggshield_step()["env"]
    assert env["GITGUARDIAN_API_KEY"] == "${{ secrets.GITGUARDIAN_API_KEY }}"


def test_secret_scan_sets_official_ci_env_vars() -> None:
    env = _ggshield_step()["env"]
    for key in (
        "GITHUB_PUSH_BEFORE_SHA",
        "GITHUB_PUSH_BASE_SHA",
        "GITHUB_PULL_BASE_SHA",
        "GITHUB_DEFAULT_BRANCH",
    ):
        assert key in env


def test_secret_scan_runs_on_push_and_internal_pull_requests() -> None:
    condition = _secret_scan_job()["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.event_name == 'pull_request'" in condition
    assert "github.event.pull_request.head.repo.full_name == github.repository" in condition


def test_secret_scan_fails_clearly_when_key_absent() -> None:
    guard = next(
        s for s in _secret_scan_job()["steps"] if "GITGUARDIAN_API_KEY" in str(s.get("run", ""))
    )
    run_text = guard["run"]
    assert 'if [ -z "$GITGUARDIAN_API_KEY" ]' in run_text
    assert "exit 1" in run_text
    assert guard["env"]["GITGUARDIAN_API_KEY"] == "${{ secrets.GITGUARDIAN_API_KEY }}"
