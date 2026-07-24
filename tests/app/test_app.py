from pathlib import Path

import pytest

from fecreator.app import AppError, FeCreatorApp, InvalidStateError
from fecreator.assets.base import SourcePlan, SubmissionSchema
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import JobResult
from fecreator.core.config import Settings
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import Registry
from fecreator.jobs.model import JobState


class _StubPortrait:
    id = "portrait"

    def required_capabilities(self, workflow: str) -> set[Capability]:
        return {Capability.TEXT_TO_IMAGE}

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        return set()

    def plan_sources(self, manifest: Manifest, pack: object) -> SourcePlan:
        return SourcePlan(
            prompts=("hero",),
            reference_roles={},
            expected_filenames=("neutral.png",),
            required_expressions=("neutral",),
            background_contract="green",
            forbidden_colors=(),
            submission_schema=SubmissionSchema(),
        )

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        return JobResult(job_id=ctx.job_id, ok=True)


def _app(tmp_path: Path) -> FeCreatorApp:
    """Isolated app: custom asset_registry, global spec/provider registries."""
    asset_reg: Registry[object] = Registry()
    asset_reg.register("portrait", _StubPortrait())
    return FeCreatorApp(Settings(data_root=tmp_path), asset_registry=asset_reg)


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def test_lists_include_registered(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert "fake" in app.list_providers()
    assert "fe-gba-portrait-standard" in app.list_specs()
    assert "portrait" in app.list_assets()


def test_isolated_asset_registry_does_not_pollute_global(tmp_path: Path) -> None:
    """Stub must not appear in the global ASSET_REGISTRY."""
    from fecreator.core.registry import ASSET_REGISTRY

    _app(tmp_path)
    assert "portrait" not in ASSET_REGISTRY.ids()


def test_create_get_and_stub_build(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    assert app.get_job(job.id).id == job.id
    result = app.build(job.id)
    assert result.ok
    # build() transitions job to WAITING_FOR_REVIEW
    assert app.get_job(job.id).state == JobState.WAITING_FOR_REVIEW


def test_plan_sources_writes_to_job_workspace(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    plan = app.plan_sources(job.id)
    assert "neutral.png" in plan.expected_filenames
    assert (tmp_path / "jobs" / job.id / "source_plan.json").exists()


def test_plan_sources_transitions_created_to_planning(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    assert job.state == JobState.CREATED
    app.plan_sources(job.id)
    assert app.get_job(job.id).state == JobState.PLANNING


def test_validate_uses_canonical_spec(tmp_path: Path) -> None:
    app = _app(tmp_path)
    diags = app.validate("fe-gba-portrait-standard", tmp_path)  # empty dir → MISSING_SHEET
    assert any(d.code == "MISSING_SHEET" for d in diags)


def test_validate_unknown_spec_raises(tmp_path: Path) -> None:
    from fecreator.app import SpecNotFoundError

    app = _app(tmp_path)
    with pytest.raises(SpecNotFoundError):
        app.validate("no-such-spec", tmp_path)


def test_build_blocked_when_cancelled(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    app.cancel(job.id)
    with pytest.raises(InvalidStateError):
        app.build(job.id)


def test_build_blocked_at_waiting_for_review(tmp_path: Path) -> None:
    """Review gate must not be bypassed."""
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    app.build(job.id)  # → WAITING_FOR_REVIEW
    with pytest.raises(InvalidStateError):
        app.build(job.id)  # blocked at review gate


def test_approve_transitions_to_validating(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    app.build(job.id)  # → WAITING_FOR_REVIEW
    record = app.approve(job.id, "build", "reviewer")
    assert record.decision == "approved"
    assert app.get_job(job.id).state == JobState.VALIDATING


def test_approve_requires_review_state(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    with pytest.raises(InvalidStateError):
        app.approve(job.id, "build", "reviewer")


def test_reject_transitions_to_failed(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    app.build(job.id)  # → WAITING_FOR_REVIEW
    record = app.reject(job.id, "build", "reviewer", "colours wrong")
    assert record.decision == "rejected"
    assert app.get_job(job.id).state == JobState.FAILED


def test_reject_blocks_further_build(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    app.build(job.id)  # → WAITING_FOR_REVIEW
    app.reject(job.id, "build", "reviewer", "colours wrong")  # → FAILED
    with pytest.raises(InvalidStateError):
        app.build(job.id)  # blocked — terminal state


def test_approve_requires_job_existence(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with pytest.raises(FileNotFoundError):
        app.approve("nonexistent-job", "build", "reviewer")


def test_submit_sources_rejects_symlinks(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    src = tmp_path / "src"
    src.mkdir()
    real = tmp_path / "secret.txt"
    real.write_text("secret")
    link = src / "link.png"
    link.symlink_to(real)
    with pytest.raises(AppError):
        app.submit_sources(job.id, src)


def test_submit_sources_rejects_hardlinks(tmp_path: Path) -> None:
    import os

    app = _app(tmp_path)
    job = app.create_job(_manifest())
    real = tmp_path / "real.png"
    real.write_bytes(b"\x89PNG")
    src = tmp_path / "src"
    src.mkdir()
    hard = src / "hard.png"
    os.link(real, hard)  # create hardlink
    with pytest.raises(AppError):
        app.submit_sources(job.id, src)


def test_submit_sources_rejects_windows_junction(tmp_path: Path) -> None:
    """Windows-specific: junction/reparse points in the source dir must be rejected."""
    import platform

    if platform.system() != "Windows":
        pytest.skip("Windows-only junction test")
    import subprocess

    app = _app(tmp_path)
    job = app.create_job(_manifest())
    target = tmp_path / "target_dir"
    target.mkdir()
    (target / "file.png").write_bytes(b"\x89PNG")
    src = tmp_path / "src"
    src.mkdir()
    junc = src / "junc"
    # Create a directory junction inside src pointing to target_dir
    result = subprocess.run(
        ["cmd", "/c", f"mklink /J {junc} {target}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("Could not create junction")
    with pytest.raises(AppError):
        app.submit_sources(job.id, src)


def test_submit_sources_no_overwrite(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    src = tmp_path / "src"
    src.mkdir()
    (src / "file.png").write_bytes(b"\x89PNG")
    app.submit_sources(job.id, src)
    with pytest.raises(AppError):
        app.submit_sources(job.id, src)  # second submit hits NO_OVERWRITE


def test_inspect_returns_job_events_and_result(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    app.build(job.id)
    data = app.inspect(job.id)
    assert data["job"]["id"] == job.id
    assert any(e["kind"] == "created" for e in data["events"])  # type: ignore[index]
    assert data["result"] is not None


def test_cancel_and_resume(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    cancelled = app.cancel(job.id)
    assert cancelled.state == JobState.CANCELLED
    resumed = app.resume(job.id)
    assert resumed.state == JobState.CANCELLED  # resume returns current state


def test_build_ok_false_transitions_to_failed(tmp_path: Path) -> None:
    """If plugin.build() returns ok=False, job transitions to FAILED."""

    class _FailPortrait(_StubPortrait):
        def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
            return JobResult(job_id=ctx.job_id, ok=False)

    asset_reg: Registry[object] = Registry()
    asset_reg.register("portrait", _FailPortrait())
    app = FeCreatorApp(Settings(data_root=tmp_path), asset_registry=asset_reg)
    job = app.create_job(_manifest())
    result = app.build(job.id)
    assert not result.ok
    assert app.get_job(job.id).state == JobState.FAILED


def test_build_exception_transitions_to_failed(tmp_path: Path) -> None:
    """If plugin.build() raises, job transitions to FAILED."""

    class _ExcPortrait(_StubPortrait):
        def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
            raise RuntimeError("plugin error")

    asset_reg: Registry[object] = Registry()
    asset_reg.register("portrait", _ExcPortrait())
    app = FeCreatorApp(Settings(data_root=tmp_path), asset_registry=asset_reg)
    job = app.create_job(_manifest())
    with pytest.raises(RuntimeError):
        app.build(job.id)
    assert app.get_job(job.id).state == JobState.FAILED


def test_generate_refuses_insufficient_capabilities(tmp_path: Path) -> None:
    """generate() checks provider capabilities; refuses with ProviderRefusal."""
    from fecreator.contracts.capabilities import CapabilitySet
    from fecreator.providers.base import ProviderRefusal

    class _NoCap:
        id = "nocap"
        capabilities = CapabilitySet(capabilities=frozenset())

        def generate(self, request: object, workspace: object) -> object:
            raise ProviderRefusal("no capabilities")

    provider_reg: Registry[object] = Registry()
    provider_reg.register("nocap", _NoCap())
    asset_reg: Registry[object] = Registry()
    asset_reg.register("portrait", _StubPortrait())

    manifest = Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="nocap",
        sources=(),
    )
    app = FeCreatorApp(
        Settings(data_root=tmp_path),
        asset_registry=asset_reg,
        provider_registry=provider_reg,
    )
    job = app.create_job(manifest)
    with pytest.raises(ProviderRefusal):
        app.generate(job.id)
