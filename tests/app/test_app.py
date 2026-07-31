from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from PIL import Image

import fecreator.references.store as reference_store
from fecreator.app import FeCreatorApp
from fecreator.assets.base import SourcePlan, SubmissionSchema
from fecreator.contracts.capabilities import Capability
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact, JobResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.config import Settings
from fecreator.core.pipeline import PipelineContext
from fecreator.core.registry import ASSET_REGISTRY
from fecreator.jobs.approvals import ApprovalError, ApprovalRecord
from fecreator.jobs.candidates import CandidateStore
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import Job, JobState
from fecreator.jobs.service import InvalidTransitionError
from fecreator.lineage.store import LineageStore
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore


class _StubAssetPlugin:
    id = "portrait"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.planned: list[tuple[Manifest, ReferencePack | None]] = []
        self.built: list[tuple[PipelineContext, Manifest]] = []
        self.finalized: tuple[Path, str, str, str] | None = None

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

    def finalize(
        self,
        *,
        data_root: Path,
        job: Job,
        candidate: CandidateSnapshot,
        approval: ApprovalRecord,
    ) -> JobResult:
        self.finalized = (data_root, job.id, candidate.job_id, approval.actor)
        return JobResult(job_id=job.id, ok=True)


_PLUGIN = _StubAssetPlugin()


@pytest.fixture(autouse=True)
def _stub_portrait_asset_registry() -> None:
    original = ASSET_REGISTRY._items.get(_PLUGIN.id)
    ASSET_REGISTRY._items[_PLUGIN.id] = _PLUGIN
    try:
        yield
    finally:
        if original is None:
            ASSET_REGISTRY._items.pop(_PLUGIN.id, None)
        else:
            ASSET_REGISTRY._items[_PLUGIN.id] = original


def _register_stub_asset() -> _StubAssetPlugin:
    _PLUGIN.reset()
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


def _candidate(job_id: str, *, lineage_id: str) -> CandidateSnapshot:
    return CandidateSnapshot(
        job_id=job_id,
        lineage_id=lineage_id,
        artifacts=(
            Artifact(
                role="concept_art",
                path="workspace/neutral.png",
                sha256="a" * 64,
                media_type="image/png",
            ),
        ),
        metrics={"score": 0.95},
        created_at="2026-07-26T00:00:00+00:00",
    )


def _lineage_node(asset_id: str, *, parents: tuple[str, ...] = ()) -> LineageNode:
    return LineageNode(
        asset_id=asset_id,
        operation=Operation.CREATE_NEUTRAL if not parents else Operation.REFINE_EXPRESSION,
        parents=parents,
        reference_pack="hero-pack",
        reference_pack_rev=2,
        created_at="2026-07-26T00:00:00+00:00",
    )


def _job_snapshot(app: FeCreatorApp, job_id: str) -> dict[str, object]:
    return app.get_job(job_id).model_dump(mode="json")


def _event_snapshots(app: FeCreatorApp, job_id: str) -> list[dict[str, object]]:
    return [event.model_dump(mode="json") for event in app.events(job_id)]


def _review_candidate(app: FeCreatorApp, data_root: Path):
    job = app.create_job(_manifest())
    candidate_id = f"{job.id}-candidate"
    LineageStore(data_root).add(_lineage_node(candidate_id))
    CandidateStore(data_root).create(_candidate(job.id, lineage_id=candidate_id))
    app._service.transition_path(
        job.id,
        (JobState.PLANNING, JobState.PROCESSING, JobState.WAITING_FOR_REVIEW),
    )
    return job


def test_finalize_job_dispatches_to_the_asset_plugin(data_root: Path) -> None:
    app, plugin = _app(data_root)
    job = _review_candidate(app, data_root)
    approval = app.approve_review(job.id, "reviewer")

    result = app.finalize_job(job.id)

    assert result == JobResult(job_id=job.id, ok=True)
    assert plugin.finalized == (data_root, job.id, job.id, approval.actor)


def test_lists_registered_items_and_gets_created_jobs(data_root: Path) -> None:
    app, _plugin = _app(data_root)

    job = app.create_job(_manifest())

    assert _PLUGIN.id in app.list_assets()
    assert "fake" in app.list_providers()
    assert "fe-gba-portrait-standard" in app.list_specs()
    assert app.get_job(job.id).model_dump(mode="json") == job.model_dump(mode="json")


def test_list_jobs_is_deterministic(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    first = app.create_job(_manifest())
    second = app.create_job(_manifest())

    assert [job.id for job in app.list_jobs()] == sorted([first.id, second.id])


def test_workbench_facade_reads_workspace_outputs_without_path_escape(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    workspace = data_root / "jobs" / job.id
    package = workspace / "package"
    bundle = workspace / "bundle"
    package.mkdir()
    bundle.mkdir()
    (package / "portrait.png").write_bytes(b"portrait")
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    (workspace / "report.json").write_text(
        json.dumps({"path": "C:\\private\\report.json"}),
        encoding="utf-8",
    )
    ReferencePackStore(data_root).create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )

    assert app.plan_job_sources(job.id).expected_filenames == ("neutral.png",)
    assert [diagnostic.code for diagnostic in app.validate_job(job.id)] == ["BAD_PNG"]
    assert app.list_reference_packs() == ["hero-pack"]
    assert app.get_job_report(job.id) == {"path": "report.json"}
    assert [entry.path for entry in app.list_bundle_entries(job.id)] == ["manifest.json"]
    assert app.read_job_artifact(job.id, "package/portrait.png") == b"portrait"
    assert app.read_bundle_file(job.id, "manifest.json") == b"{}"
    with pytest.raises(ValueError, match="unsafe"):
        app.read_job_artifact(job.id, "../private.txt")


def test_read_methods_return_candidates_approvals_references_and_lineage(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    refs = ReferencePackStore(data_root)
    refs.create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    refs.new_revision("hero-pack", provenance="approved-update")
    lineage = LineageStore(data_root)
    lineage.add(_lineage_node("root"))
    lineage.add(_lineage_node("child-a", parents=("root",)))
    lineage.add(_lineage_node("child-b", parents=("root",)))
    lineage.add(
        LineageNode(
            asset_id="final",
            operation=Operation.EXPORT_SPEC,
            parents=("child-a", "child-b"),
            reference_pack="hero-pack",
            reference_pack_rev=2,
            created_at="2026-07-26T00:00:00+00:00",
        )
    )
    candidate = CandidateStore(data_root).create(_candidate(job.id, lineage_id="final"))
    app.approve(job.id, "plan", "alice")
    app.reject(job.id, "review", "bob", "needs changes")

    assert app.get_job_candidate(job.id) == candidate
    assert [decision.stage for decision in app.list_approval_decisions(job.id)] == [
        "plan",
        "review",
    ]
    assert app.get_reference_pack("hero-pack", 1).revision == 1
    assert [pack.revision for pack in app.list_reference_history("hero-pack")] == [1, 2]
    assert app.get_lineage("final").parents == ("child-a", "child-b")
    assert [node.asset_id for node in app.list_lineage_ancestors("final")] == [
        "child-a",
        "child-b",
        "root",
    ]
    assert [node.asset_id for node in app.list_lineage_children("root")] == [
        "child-a",
        "child-b",
    ]


def test_list_approval_decisions_rejects_unknown_job(data_root: Path) -> None:
    app, _plugin = _app(data_root)

    with pytest.raises(FileNotFoundError):
        app.list_approval_decisions("missing-job")


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


def test_create_job_pins_latest_reference_revision(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    store = ReferencePackStore(data_root)
    store.create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    store.new_revision("hero-pack", provenance="approved-update")

    job = app.create_job(_manifest(character_ref_pack="hero-pack"))

    assert job.manifest.character_ref_pack_rev == 2
    assert app.get_job(job.id).manifest.character_ref_pack_rev == 2


def test_pinned_job_ignores_later_reference_revision(data_root: Path, tmp_path: Path) -> None:
    app, plugin = _app(data_root)
    store = ReferencePackStore(data_root)
    store.create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    job = app.create_job(_manifest(provider="manual", character_ref_pack="hero-pack"))
    store.new_revision("hero-pack", provenance="approved-update", traits={"hair": "blue"})

    app.plan_sources(job.id, tmp_path / "manual-plan")

    assert plugin.planned[0][1] is not None
    assert plugin.planned[0][1].revision == 1
    assert app.get_job(job.id).manifest.character_ref_pack_rev == 1


def test_legacy_unpinned_persisted_job_fails_closed(data_root: Path, tmp_path: Path) -> None:
    app, plugin = _app(data_root)
    store = ReferencePackStore(data_root)
    store.create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    job = app.create_job(_manifest(provider="manual", character_ref_pack="hero-pack"))
    manifest_path = data_root / "jobs" / job.id / "manifest.json"
    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    persisted_manifest.pop("character_ref_pack_rev")
    manifest_path.write_text(json.dumps(persisted_manifest), encoding="utf-8")

    assert hasattr(reference_store, "UnpinnedReferencePackError")

    with pytest.raises(reference_store.UnpinnedReferencePackError, match="character_ref_pack_rev"):
        app.plan_sources(job.id, tmp_path / "manual-plan")

    assert plugin.planned == []


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


def test_submit_sources_created_path_event_failure_restores_original_snapshot(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    original_job = _job_snapshot(app, job.id)
    original_events = _event_snapshots(app, job.id)
    incoming = tmp_path / "incoming"
    _write_png(incoming / "neutral.png")
    original_append_many = app._service._events.append_many

    def fail_target_transition(job_id: str, events):
        if any(event[1] == "planning->waiting_for_sources" for event in events):
            raise OSError("event boom")
        return original_append_many(job_id, events)

    monkeypatch.setattr(app._service._events, "append_many", fail_target_transition)

    with pytest.raises(OSError, match="event boom"):
        app.submit_sources(job.id, incoming)

    assert _job_snapshot(app, job.id) == original_job
    assert _event_snapshots(app, job.id) == original_events
    assert not (data_root / "jobs" / job.id / "submitted").exists()
    assert not list((data_root / "jobs" / job.id).glob(".submitted-stage-*"))


def test_submit_sources_rejects_unsafe_symlinks_without_replacing_existing_snapshot(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    app.plan_sources(job.id, tmp_path / "plan")
    original_job = _job_snapshot(app, job.id)
    original_events = _event_snapshots(app, job.id)

    unsafe_batch = tmp_path / "unsafe"
    _write_png(unsafe_batch / "neutral.png")
    outside = tmp_path / "outside.png"
    _write_png(outside)
    try:
        (unsafe_batch / "escape.png").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(ValueError, match="unsafe|symlink|reparse"):
        app.submit_sources(job.id, unsafe_batch)

    assert _job_snapshot(app, job.id) == original_job
    assert _event_snapshots(app, job.id) == original_events
    assert not (data_root / "jobs" / job.id / "submitted").exists()
    assert not list((data_root / "jobs" / job.id).glob(".submitted-stage-*"))


def test_submit_sources_missing_directory_leaves_fake_job_state_unchanged(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    app.plan_sources(job.id, tmp_path / "plan")
    original_job = _job_snapshot(app, job.id)
    original_events = _event_snapshots(app, job.id)

    with pytest.raises(FileNotFoundError):
        app.submit_sources(job.id, tmp_path / "missing")

    assert _job_snapshot(app, job.id) == original_job
    assert _event_snapshots(app, job.id) == original_events
    assert not (data_root / "jobs" / job.id / "submitted").exists()


def test_submit_sources_copy_failure_leaves_fake_job_state_unchanged(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    app.plan_sources(job.id, tmp_path / "plan")
    original_job = _job_snapshot(app, job.id)
    original_events = _event_snapshots(app, job.id)
    incoming = tmp_path / "incoming"
    _write_png(incoming / "neutral.png")
    _write_png(incoming / "blink.png")
    original_copy = app._copy_regular_file
    copied_paths: list[Path] = []

    def fail_after_first_copy(source: Path, destination: Path) -> None:
        copied_paths.append(destination)
        original_copy(source, destination)
        if destination.name == "blink.png":
            raise OSError("copy boom")

    monkeypatch.setattr(app, "_copy_regular_file", fail_after_first_copy)

    with pytest.raises(OSError, match="copy boom"):
        app.submit_sources(job.id, incoming)

    assert [path.name for path in copied_paths] == ["blink.png"]
    assert _job_snapshot(app, job.id) == original_job
    assert _event_snapshots(app, job.id) == original_events
    assert not (data_root / "jobs" / job.id / "submitted").exists()
    assert not list((data_root / "jobs" / job.id).glob(".submitted-stage-*"))


def test_submit_sources_rejects_second_submission_without_replacing_existing_snapshot(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest(provider="manual"))
    app.plan_sources(job.id, tmp_path / "plan")
    first_batch = tmp_path / "first"
    _write_png(first_batch / "neutral.png")
    app.submit_sources(job.id, first_batch)
    submitted_path = data_root / "jobs" / job.id / "submitted" / "neutral.png"
    original_bytes = submitted_path.read_bytes()
    original_job = _job_snapshot(app, job.id)
    original_events = _event_snapshots(app, job.id)

    second_batch = tmp_path / "second"
    _write_png(second_batch / "neutral.png")

    with pytest.raises(FileExistsError, match="submitted sources already exist"):
        app.submit_sources(job.id, second_batch)

    assert submitted_path.read_bytes() == original_bytes
    assert _job_snapshot(app, job.id) == original_job
    assert _event_snapshots(app, job.id) == original_events


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


def test_approve_review_records_actor_and_rejects_a_second_decision(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    job = _review_candidate(app, data_root)

    approved = app.approve_review(job.id, actor="reviewer")

    assert approved.stage == "candidate"
    assert approved.actor == "reviewer"
    assert app.events(job.id)[-1].kind == "review_approved"
    assert app.events(job.id)[-1].data == {"actor": "reviewer"}
    with pytest.raises(ApprovalError):
        app.approve_review(job.id, actor="other-reviewer")
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW


def test_reject_review_preserves_candidate_and_fails_job(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    job = _review_candidate(app, data_root)

    rejected = app.reject_review(job.id, actor="reviewer", reason="bad silhouette")

    assert rejected.decision == "rejected"
    assert app.get_job(job.id).state is JobState.FAILED
    assert app.get_job_candidate(job.id).job_id == job.id
    assert app.events(job.id)[-1].kind == "review_rejected"
    assert app.events(job.id)[-1].data == {"actor": "reviewer"}
    with pytest.raises(InvalidTransitionError, match="failed is not waiting_for_review"):
        app.reject_review(job.id, actor="other-reviewer", reason="still bad")
    assert app.list_approval_decisions(job.id) == [rejected]


@pytest.mark.parametrize(
    ("path", "state"),
    (
        ((), JobState.CREATED),
        ((JobState.PLANNING, JobState.PROCESSING), JobState.PROCESSING),
        ((JobState.PLANNING, JobState.PROCESSING, JobState.FAILED), JobState.FAILED),
        (
            (JobState.PLANNING, JobState.PROCESSING, JobState.VALIDATING, JobState.COMPLETED),
            JobState.COMPLETED,
        ),
        ((JobState.CANCELLED,), JobState.CANCELLED),
    ),
)
def test_reject_review_requires_waiting_for_review_without_mutating(
    data_root: Path,
    path: tuple[JobState, ...],
    state: JobState,
) -> None:
    app, _plugin = _app(data_root)
    job = app.create_job(_manifest())
    if path == (JobState.CANCELLED,):
        app.cancel(job.id)
    elif path:
        app._service.transition_path(job.id, path)
    before_job = _job_snapshot(app, job.id)
    before_events = _event_snapshots(app, job.id)

    with pytest.raises(InvalidTransitionError, match="is not waiting_for_review"):
        app.reject_review(job.id, actor="reviewer", reason="bad silhouette")

    assert app.get_job(job.id).state is state
    assert _job_snapshot(app, job.id) == before_job
    assert _event_snapshots(app, job.id) == before_events
    assert app.list_approval_decisions(job.id) == []


def test_reject_review_rechecks_state_after_a_concurrent_transition(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _plugin = _app(data_root)
    job = _review_candidate(app, data_root)
    processing_transition_started = threading.Event()
    allow_processing_transition = threading.Event()
    rejection_errors: list[Exception] = []
    original_append_many = EventLog.append_many

    def pause_processing_transition(self, job_id: str, events):
        if any(message == "waiting_for_review->processing" for _kind, message, _data in events):
            processing_transition_started.set()
            assert allow_processing_transition.wait(timeout=5)
        return original_append_many(self, job_id, events)

    def transition_to_processing() -> None:
        app._service.transition(job.id, JobState.PROCESSING)

    def reject_review() -> None:
        try:
            app.reject_review(job.id, actor="reviewer", reason="bad silhouette")
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            rejection_errors.append(exc)

    monkeypatch.setattr(EventLog, "append_many", pause_processing_transition)
    transition_thread = threading.Thread(target=transition_to_processing)
    rejection_thread = threading.Thread(target=reject_review)
    transition_thread.start()
    try:
        assert processing_transition_started.wait(timeout=5)
        rejection_thread.start()
        assert rejection_thread.is_alive()
    finally:
        allow_processing_transition.set()
        transition_thread.join(timeout=5)
        rejection_thread.join(timeout=5)

    assert not transition_thread.is_alive()
    assert not rejection_thread.is_alive()
    assert len(rejection_errors) == 1
    assert isinstance(rejection_errors[0], InvalidTransitionError)
    assert "processing is not waiting_for_review" in str(rejection_errors[0])
    assert app.get_job(job.id).state is JobState.PROCESSING
    assert app.list_approval_decisions(job.id) == []
    assert all(event.kind != "review_rejected" for event in app.events(job.id))


def test_reject_review_rolls_back_its_pending_approval_when_event_logging_fails(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _plugin = _app(data_root)
    job = _review_candidate(app, data_root)
    original_append_many = EventLog.append_many

    def fail_rejection_transition(self, job_id: str, events):
        if any(message == "waiting_for_review->failed" for _kind, message, _data in events):
            raise OSError("review event failed")
        return original_append_many(self, job_id, events)

    monkeypatch.setattr(EventLog, "append_many", fail_rejection_transition)

    with pytest.raises(OSError, match="review event failed"):
        app.reject_review(job.id, actor="reviewer", reason="bad silhouette")

    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW
    assert app.get_job_candidate(job.id).job_id == job.id
    assert app.list_approval_decisions(job.id) == []


def test_generic_approval_waits_for_review_rollback_before_appending(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _plugin = _app(data_root)
    job = _review_candidate(app, data_root)
    rejection_recorded = threading.Event()
    allow_rejection_event_failure = threading.Event()
    generic_finished = threading.Event()
    review_errors: list[Exception] = []
    generic_errors: list[Exception] = []
    original_append_many = EventLog.append_many

    def fail_after_rejection_is_recorded(self, job_id: str, events):
        if any(message == "waiting_for_review->failed" for _kind, message, _data in events):
            rejection_recorded.set()
            assert allow_rejection_event_failure.wait(timeout=5)
            raise OSError("review event failed")
        return original_append_many(self, job_id, events)

    def reject_review() -> None:
        try:
            app.reject_review(job.id, actor="reviewer", reason="bad silhouette")
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            review_errors.append(exc)

    def add_plan_approval() -> None:
        try:
            app.approve(job.id, "plan", "other-reviewer")
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            generic_errors.append(exc)
        finally:
            generic_finished.set()

    monkeypatch.setattr(EventLog, "append_many", fail_after_rejection_is_recorded)
    review_thread = threading.Thread(target=reject_review)
    generic_thread = threading.Thread(target=add_plan_approval)
    review_thread.start()
    try:
        assert rejection_recorded.wait(timeout=5)
        generic_thread.start()
        assert not generic_finished.wait(timeout=0.1)
    finally:
        allow_rejection_event_failure.set()
        review_thread.join(timeout=5)
        generic_thread.join(timeout=5)

    assert not review_thread.is_alive()
    assert not generic_thread.is_alive()
    assert len(review_errors) == 1
    assert isinstance(review_errors[0], OSError)
    assert generic_errors == []
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW
    assert [record.stage for record in app.list_approval_decisions(job.id)] == ["plan"]


def test_retry_creates_one_linked_immutable_job(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    rejected = _review_candidate(app, data_root)
    app.reject_review(rejected.id, actor="reviewer", reason="bad silhouette")

    retry = app.retry_job(rejected.id, actor="reviewer")

    assert retry.id != rejected.id
    assert retry.parent_candidate_id == f"{rejected.id}-candidate"
    assert app.get_job(retry.id).parent_candidate_id == f"{rejected.id}-candidate"
    assert retry.state is JobState.CREATED
    assert app.events(retry.id)[-1].kind == "retry_created"
    assert app.events(retry.id)[-1].data == {"actor": "reviewer"}
    with pytest.raises(InvalidTransitionError, match="retry already created"):
        app.retry_job(rejected.id, actor="other-reviewer")


def _package_workspace(app: FeCreatorApp, data_root: Path) -> tuple[str, Path]:
    job = app.create_job(_manifest())
    workspace = data_root / "jobs" / job.id
    (workspace / "package").mkdir()
    (workspace / "package" / "portrait.png").write_bytes(b"final")
    (workspace / "candidate" / "package").mkdir(parents=True)
    (workspace / "candidate" / "package" / "portrait.png").write_bytes(b"candidate")
    (workspace / "candidate" / "candidate.json").write_text("{}", encoding="utf-8")
    (workspace / "bundle").mkdir()
    (workspace / "bundle" / "manifest.json").write_text("{}", encoding="utf-8")
    (workspace / "report.json").write_text("{}", encoding="utf-8")
    (workspace / "lineage.json").write_text("[]", encoding="utf-8")
    return job.id, workspace


@pytest.mark.parametrize(
    "relative_path",
    [
        "job.json",
        "manifest.json",
        "events.jsonl",
        "report.json",
        "lineage.json",
        "candidate/candidate.json",
        "bundle/manifest.json",
    ],
)
def test_read_job_artifact_only_serves_package_artifacts(
    data_root: Path,
    relative_path: str,
) -> None:
    app, _plugin = _app(data_root)
    job_id, _workspace = _package_workspace(app, data_root)

    assert app.read_job_artifact(job_id, "package/portrait.png") == b"final"
    assert app.read_job_artifact(job_id, "candidate/package/portrait.png") == b"candidate"
    with pytest.raises(ValueError, match="package artifact"):
        app.read_job_artifact(job_id, relative_path)


def test_workspace_reads_reject_backslash_separated_paths(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    job_id, _workspace = _package_workspace(app, data_root)

    with pytest.raises(ValueError, match="unsafe"):
        app.read_job_artifact(job_id, "package\\portrait.png")
    with pytest.raises(ValueError, match="unsafe"):
        app.read_bundle_file(job_id, "..\\..\\report.json")


def test_workspace_reads_reject_symlinked_artifacts_when_supported(data_root: Path) -> None:
    app, _plugin = _app(data_root)
    job_id, workspace = _package_workspace(app, data_root)
    outside = data_root.parent / "outside.png"
    outside.write_bytes(b"secret")
    try:
        (workspace / "package" / "link.png").symlink_to(outside)
        (workspace / "bundle" / "link.json").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(ValueError, match="unsafe"):
        app.read_job_artifact(job_id, "package/link.png")
    with pytest.raises(ValueError, match="unsafe"):
        app.read_bundle_file(job_id, "link.json")
