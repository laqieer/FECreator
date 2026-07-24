from pathlib import Path

from fecreator.app import FeCreatorApp
from fecreator.assets.base import SourcePlan
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import JobResult
from fecreator.core.config import Settings
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY


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
            submission_schema={},
        )

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        return JobResult(job_id=ctx.job_id, ok=True)


def _app(tmp_path: Path) -> FeCreatorApp:
    if "portrait" not in ASSET_REGISTRY.ids():
        ASSET_REGISTRY.register("portrait", _StubPortrait())
    return FeCreatorApp(Settings(data_root=tmp_path))


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


def test_create_get_and_stub_build(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    assert app.get_job(job.id).id == job.id
    assert app.build(job.id).ok


def test_plan_sources_writes_file(tmp_path: Path) -> None:
    app = _app(tmp_path)
    job = app.create_job(_manifest())
    plan = app.plan_sources(job.id, tmp_path / "plan")
    assert "neutral.png" in plan.expected_filenames
    assert (tmp_path / "plan" / "source_plan.json").exists()


def test_validate_uses_spec(tmp_path: Path) -> None:
    app = _app(tmp_path)
    diags = app.validate("fe-gba-portrait-standard", tmp_path)  # empty dir -> MISSING_SHEET
    assert any(d.code == "MISSING_SHEET" for d in diags)
