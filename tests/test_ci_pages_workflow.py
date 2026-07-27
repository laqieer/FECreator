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


RELEASE_GATE_JOBS = frozenset(
    {"python", "web", "browser", "package", "febuilder-interop", "secret-scan"}
)


def test_deploy_pages_needs_all_build_and_test_jobs() -> None:
    assert set(_deploy_job()["needs"]) == RELEASE_GATE_JOBS


def test_pages_deploy_requires_all_release_gates() -> None:
    assert set(_deploy_job()["needs"]) >= RELEASE_GATE_JOBS


def _step_text(job: dict) -> str:
    return " ".join(str(step.get("run", "")) for step in job["steps"])


def _uses(job: dict) -> list[str]:
    return [str(step.get("uses", "")) for step in job["steps"]]


def test_browser_job_runs_on_every_push_and_pull_request() -> None:
    browser = _job("browser")
    assert "if" not in browser
    triggers = _triggers()
    assert "push" in triggers and "pull_request" in triggers


def test_browser_job_installs_node_python_and_playwright_chromium() -> None:
    browser = _job("browser")
    uses = _uses(browser)
    assert any(u.startswith("actions/setup-node@") for u in uses)
    assert any(u.startswith("actions/setup-python@") for u in uses)

    run_text = _step_text(browser)
    assert "npm ci" in run_text
    assert 'pip install -e ".[dev]"' in run_text
    assert "playwright install --with-deps chromium" in run_text


def test_browser_job_runs_the_local_and_demo_end_to_end_suite() -> None:
    assert "npm run -w @laqieer/fecreator-web test:e2e" in _step_text(_job("browser"))


def test_browser_job_points_playwright_at_a_quoted_python_path() -> None:
    """The interpreter path is quoted, so a path containing spaces still runs."""
    e2e_step = next(
        step for step in _job("browser")["steps"] if "test:e2e" in str(step.get("run", ""))
    )
    python_path = e2e_step["env"]["FECREATOR_PYTHON"]

    assert python_path.startswith('"') and python_path.endswith('"')
    assert "python" in python_path


def test_browser_job_uploads_the_playwright_output_directory_on_failure() -> None:
    """Traces are retained on failure, so the uploaded path must be outputDir."""
    upload = next(
        step
        for step in _job("browser")["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )

    assert upload["if"] == "failure()"
    assert upload["with"]["path"] == "web/test-results"

    config = (REPO_ROOT / "web" / "playwright.config.ts").read_text(encoding="utf-8")
    # Playwright only writes `playwright-report/` with the html reporter, which
    # this project does not enable; traces go to the default `test-results/`.
    assert "playwright-report" not in config
    assert '"html"' not in config


def test_febuilder_interop_job_always_runs_the_deterministic_tests() -> None:
    interop = _job("febuilder-interop")
    assert "if" not in interop

    roundtrip_step = next(
        step
        for step in interop["steps"]
        if "tests/interop/test_febuilder_roundtrip.py" in str(step.get("run", ""))
    )
    assert "if" not in roundtrip_step


def test_febuilder_interop_external_smoke_is_opt_in_through_a_repository_variable() -> None:
    interop = _job("febuilder-interop")
    smoke = next(step for step in interop["steps"] if "FEBUILDER_CLI" in str(step.get("env", {})))

    assert smoke["if"] == "${{ vars.FEBUILDER_CLI != '' }}"
    assert smoke["env"]["FEBUILDER_CLI"] == "${{ vars.FEBUILDER_CLI }}"
    assert "tests/interop/test_febuilder_cli_smoke.py" in smoke["run"]


def test_febuilder_interop_job_never_requires_a_rom() -> None:
    interop = _job("febuilder-interop")
    env_keys = {key for step in interop["steps"] for key in (step.get("env") or {})}

    assert env_keys <= {"FEBUILDER_CLI"}
    assert not any("ROM" in key.upper() for key in env_keys)
    assert "rom" not in _step_text(interop).lower().replace("from", "")


def test_release_gate_jobs_are_declared() -> None:
    jobs = _workflow()["jobs"]
    assert set(jobs) >= RELEASE_GATE_JOBS


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
