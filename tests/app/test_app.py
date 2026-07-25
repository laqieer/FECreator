from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from fecreator.app import FeCreatorApp
from fecreator.assets.base import SourcePlan, SubmissionSchema
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import JobResult
from fecreator.core.config import Settings
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY
from fecreator.jobs.model import JobState
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore


class _StubAssetPlugin:
    id = "portrait"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.planned: list[tuple[Manifest, ReferencePack | None]] = []
        self.built: list[tuple[PipelineContext, Manifest]] = []

    def required_capabilities(self, workflow: str) -> set[Capability]:
        del workflow
        return {Capability.TEXT_TO_IMAGE}

    def preferred_capabilities(self, workflow: str) -> set[Capability]:
        del workflow
        return set()

    def plan_sources(self, manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
        self.planned.append((manifest, pack))
        return SourcePlan(
            prompts=("hero",),
            reference_roles={},
            expected_filenames=("neutral.png",),
            required_expressions=("neutral",),
            background_contract="green background required",
            forbidden_colors=(),
            submission_schema=SubmissionSchema(
                provenance=pack.provenance if pack is not None else "",
                rights=pack.rights if pack is not None else "",
            ),
        )

    def build(self, ctx: PipelineContext, manifest: Manifest) -> JobResult:
        self.built.append((ctx, manifest))
        return JobResult(job_id=ctx.job_id, ok=True)


_PLUGIN = _StubAssetPlugin()


def _register_stub_asset() -> _StubAssetPlugin:
    _PLUGIN.reset()
    if _PLUGIN.id not in ASSET_REGISTRY.ids():
        ASSET_REGISTRY.register(_PLUGIN.id, _PLUGIN)
    return _PLUGIN


def _app(data_root: Path) -> tuple[FeCreatorApp, _StubAssetPlugin]:
    plugin = _register_stub_asset()
    return FeCreatorApp(Settings(data_root=data_root)), plugin


def _manifest(
    *,
    provider: str = "fake",
    character_ref_pack: str | None = None,
) -> Manifest:
    return Manifest(
        asset_type=_PLUGIN.id,
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider=provider,
        character_ref_pack=character_ref_pack,
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1, 1), color=(0, 248, 0)).save(path, format="PNG")


def test_lists_registered_items_and_gets_created_jobs(data_root: Path) -> None:
    app, _plugin = _app(data_root)

    job = app.create_job(_manifest())

    assert _PLUGIN.id in app.list_assets()
    assert "fake" in app.list_providers()
    assert "fe-gba-portrait-standard" in app.list_specs()
    assert app.get_job(job.id).model_dump(mode="json") == job.model_dump(mode="json")


def test_plan_sources_writes_file_loads_refs_and_moves_job_to_waiting_state(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app, plugin = _app(data_root)
    ReferencePackStore(data_root).create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    manual_job = app.create_job(_manifest(provider="manual", character_ref_pack="hero-pack"))
    fake_job = app.create_job(_manifest(provider="fake"))

    manual_plan = app.plan_sources(manual_job.id, tmp_path / "manual-plan")
    app.plan_sources(fake_job.id, tmp_path / "fake-plan")

    assert manual_plan.expected_filenames == ("neutral.png",)
    assert plugin.planned[0][1] is not None
    assert plugin.planned[0][1].id == "hero-pack"
    assert plugin.planned[0][1].revision == 1
    assert app.get_job(manual_job.id).state is JobState.WAITING_FOR_SOURCES
    assert app.get_job(fake_job.id).state is JobState.WAITING_FOR_PROVIDER
    assert (
        json.loads((tmp_path / "manual-plan" / "source_plan.json").read_text(encoding="utf-8"))[
            "submission_schema"
        ]["provenance"]
        == "approved-board"
    )
    assert json.loads((tmp_path / "fake-plan" / "source_plan.json").read_text(encoding="utf-8"))[
        "expected_filenames"
    ] == ["neutral.png"]


def test_submit_sources_copies_files_and_records_event(data_root: Path, tmp_path: Path) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest(provider="manual"))
    app.plan_sources(job.id, tmp_path / "plan")
    incoming = tmp_path / "incoming"
    _write_png(incoming / "neutral.png")

    returned = app.submit_sources(job.id, incoming)

    submitted = data_root / "jobs" / job.id / "submitted" / "neutral.png"
    assert returned.id == job.id
    assert submitted.exists()
    assert app.get_job(job.id).state is JobState.WAITING_FOR_SOURCES
    assert [event.kind for event in app.events(job.id)] == [
        "created",
        "transition",
        "transition",
        "sources_submitted",
    ]
    assert app.events(job.id)[-1].kind == "sources_submitted"


def test_submit_sources_rejects_unsafe_symlinks_without_replacing_existing_snapshot(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest(provider="manual"))
    app.plan_sources(job.id, tmp_path / "plan")

    first_batch = tmp_path / "first"
    _write_png(first_batch / "neutral.png")
    app.submit_sources(job.id, first_batch)

    unsafe_batch = tmp_path / "unsafe"
    _write_png(unsafe_batch / "replacement.png")
    outside = tmp_path / "outside.png"
    _write_png(outside)
    try:
        (unsafe_batch / "escape.png").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(ValueError, match="unsafe|symlink|reparse"):
        app.submit_sources(job.id, unsafe_batch)

    submitted_dir = data_root / "jobs" / job.id / "submitted"
    assert sorted(path.name for path in submitted_dir.iterdir()) == ["neutral.png"]


def test_build_validate_approvals_cancel_and_events(data_root: Path, tmp_path: Path) -> None:
    app, plugin = _app(data_root)
    job = app.create_job(_manifest())

    result = app.build(job.id)
    approved = app.approve(job.id, "plan", "alice")
    rejected = app.reject(job.id, "review", "bob", "needs changes")
    cancelled = app.cancel(job.id)
    diagnostics = app.validate("fe-gba-portrait-standard", tmp_path)

    assert result.ok is True
    assert plugin.built[-1][0].workspace == data_root / "jobs" / job.id
    assert plugin.built[-1][1].provider == "fake"
    assert approved.decision == "approved"
    assert rejected.decision == "rejected"
    assert cancelled.state is JobState.CANCELLED
    assert any(diagnostic.code == "MISSING_SHEET" for diagnostic in diagnostics)
    assert [event.kind for event in app.events(job.id)] == ["created", "transition"]
