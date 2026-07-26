from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

import fecreator.references.store as reference_store
from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import has_errors, warning
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.pipeline import PipelineContext
from fecreator.imaging.io import save_png
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import JobState
from fecreator.jobs.service import InvalidTransitionError, JobService
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard


def _manifest(
    workflow: str = "text_to_portrait",
    sources: tuple[SourceSpec, ...] | None = None,
) -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow=workflow,
        provider="fake",
        sources=sources or (SourceSpec(kind="text", ref="a brave knight"),),
    )


def _portrait_rgb() -> np.ndarray:
    rgb = np.full((80, 96, 3), (0, 248, 0), dtype=np.uint8)
    rgb[20:60, 20:60] = (200, 40, 40)
    return rgb


def _background_rgb() -> np.ndarray:
    return np.full((80, 96, 3), (0, 248, 0), dtype=np.uint8)


@pytest.fixture
def isolated_app_asset_bootstrap() -> None:
    import fecreator
    from fecreator.core.registry import ASSET_REGISTRY, PROVIDER_REGISTRY, SPEC_REGISTRY

    saved_registries = {
        ASSET_REGISTRY: dict(ASSET_REGISTRY._items),
        PROVIDER_REGISTRY: dict(PROVIDER_REGISTRY._items),
        SPEC_REGISTRY: dict(SPEC_REGISTRY._items),
    }
    saved_modules = {
        name: sys.modules.get(name)
        for name in ("fecreator.assets", "fecreator.app", "fecreator.providers", "fecreator.specs")
    }

    for registry in saved_registries:
        registry._items.clear()
    for name in saved_modules:
        sys.modules.pop(name, None)
        if "." in name:
            _, child = name.split(".", 1)
            if hasattr(fecreator, child):
                delattr(fecreator, child)
    try:
        yield
    finally:
        for registry, items in saved_registries.items():
            registry._items.clear()
            registry._items.update(items)
        for name, module in saved_modules.items():
            _, child = name.split(".", 1)
            if module is None:
                sys.modules.pop(name, None)
                if hasattr(fecreator, child):
                    delattr(fecreator, child)
            else:
                sys.modules[name] = module
                setattr(fecreator, child, module)


def test_plugin_required_caps() -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    assert PortraitPlugin().required_capabilities("text_to_portrait") == {Capability.TEXT_TO_IMAGE}


def test_build_produces_valid_candidate_package_and_lineage(data_root: Path) -> None:
    import fecreator.providers  # noqa: F401
    from fecreator.assets.portrait.plugin import PortraitPlugin

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    assert result.lineage_id == f"{job.id}-candidate"
    package = ctx.workspace / "candidate" / "package"
    assert not has_errors(FeGbaPortraitStandard().validate(package))
    assert LineageStore(data_root).get(f"{job.id}-candidate").operation.value == "create_neutral"
    assert JobStore(data_root).load(job.id).state.value == "waiting_for_review"
    assert (ctx.workspace / "candidate" / "candidate.json").exists()
    assert not (ctx.workspace / "package").exists()
    assert not (ctx.workspace / "report.json").exists()
    assert not (ctx.workspace / "lineage.json").exists()
    assert not (ctx.workspace / "bundle").exists()


def test_concept_build_requires_concept_input(data_root: Path) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    job = JobStore(data_root).create(_manifest("concept_to_portrait"))
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is False
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"WORKFLOW_INPUT_MISSING"}
    assert JobStore(data_root).load(job.id).state.value == "failed"


def test_concept_build_passes_submitted_art_to_image_provider(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    requests: list[GenRequest] = []

    class _ImageProvider:
        id = "image-only"
        capabilities = CapabilitySet(capabilities=frozenset({Capability.IMAGE_TO_IMAGE}))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            requests.append(request)
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="7" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    job = JobStore(data_root).create(
        _manifest(
            "concept_to_portrait",
            (SourceSpec(kind="concept_art", ref="concept.png"),),
        )
    )
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    save_png(ctx.workspace / "submitted" / "concept.png", _portrait_rgb())
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _ImageProvider()
    )

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    assert requests[0].references[0].path == "submitted/concept.png"
    assert LineageStore(data_root).get(f"{job.id}-candidate").operation.value == "import_concept"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("asset_type", "battle-animation", "asset_type='portrait'"),
        ("target_spec", "fe-gba-map-sprite-standard", "target_spec='fe-gba-portrait-standard'"),
    ],
)
def test_build_rejects_unsupported_manifest_scope_before_state_transition(
    data_root: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    invalid_manifest = job.manifest.model_copy(update={field: value})

    with pytest.raises(ValueError, match=message):
        PortraitPlugin().build(ctx, invalid_manifest)

    assert JobStore(data_root).load(job.id).state.value == "created"
    assert EventLog(data_root).read(job.id) == []


def test_build_selects_neutral_artifact_by_role(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-role-order"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            save_png(workspace / "generated" / "preview.png", _background_rgb())
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="preview",
                        path="generated/preview.png",
                        sha256="0" * 64,
                        media_type="image/png",
                    ),
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="1" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    assert not has_errors(FeGbaPortraitStandard().validate(ctx.workspace / "candidate" / "package"))


def test_build_carries_provider_diagnostics_to_candidate_and_review_state(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    provider_diag = warning("PROVIDER_NOTE", "provider reported a non-fatal note")

    class _Provider:
        id = "stub-diags"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="2" * 64,
                        media_type="image/png",
                    ),
                ),
                diagnostics=(provider_diag,),
            )

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    result = PortraitPlugin().build(ctx, job.manifest)
    stored_job = JobStore(data_root).load(job.id)

    assert result.ok is True
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_NOTE"}
    assert stored_job.state.value == "waiting_for_review"
    assert [event.message for event in EventLog(data_root).read(job.id)] == [
        "created->planning",
        "planning->processing",
        "processing->waiting_for_review",
    ]
    assert not (ctx.workspace / "report.json").exists()
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_NOTE"}


def test_reference_pack_lookup_uses_pinned_revision(data_root: Path) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    store = ReferencePackStore(data_root)
    store.create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            concept_art=(
                Artifact(
                    role="concept_art",
                    path="incoming/rev1.png",
                    sha256="1" * 64,
                    media_type="image/png",
                ),
            ),
            provenance="approved-board",
            rights="original",
        )
    )
    store.new_revision(
        "hero-pack",
        concept_art=(
            Artifact(
                role="concept_art",
                path="incoming/rev2.png",
                sha256="2" * 64,
                media_type="image/png",
            ),
        ),
        provenance="approved-update",
    )

    manifest = cast(
        Manifest,
        SimpleNamespace(character_ref_pack="hero-pack", character_ref_pack_rev=1),
    )

    pack = PortraitPlugin()._reference_pack(data_root, manifest)

    assert pack.revision == 1
    assert pack.concept_art[0].path == "incoming/rev1.png"


def test_reference_pack_lookup_rejects_unpinned_legacy_manifest(data_root: Path) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    ReferencePackStore(data_root).create(
        ReferencePack(
            id="hero-pack",
            revision=99,
            provenance="approved-board",
            rights="original",
        )
    )
    manifest = cast(
        Manifest,
        SimpleNamespace(character_ref_pack="hero-pack", character_ref_pack_rev=None),
    )

    assert hasattr(reference_store, "UnpinnedReferencePackError")

    with pytest.raises(reference_store.UnpinnedReferencePackError, match="character_ref_pack_rev"):
        PortraitPlugin()._reference_pack(data_root, manifest)


def test_build_rolls_back_candidate_when_review_event_logging_fails(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-completed-event-fail"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="3" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    original_append_many = plugin_module.EventLog.append_many

    def fail_review_transition(self, job_id: str, events):
        if any(
            kind == "transition" and message == "processing->waiting_for_review"
            for kind, message, _ in events
        ):
            raise OSError("transition event failed")
        return original_append_many(self, job_id, events)

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())
    monkeypatch.setattr(plugin_module.EventLog, "append_many", fail_review_transition)

    with pytest.raises(OSError, match="transition event failed"):
        PortraitPlugin().build(ctx, job.manifest)

    with pytest.raises(FileNotFoundError):
        LineageStore(data_root).get(f"{job.id}-candidate")
    assert JobStore(data_root).load(job.id).state.value == "processing"
    assert [event.message for event in EventLog(data_root).read(job.id)] == [
        "created->planning",
        "planning->processing",
    ]
    assert not (ctx.workspace / "candidate").exists()


def test_build_rolls_back_publication_when_lineage_store_add_fails(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-lineage-store-fail"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="3" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    def fail_lineage_add(self, node):
        raise OSError("lineage store failed")

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())
    import fecreator.assets.portrait.candidate as candidate_module

    monkeypatch.setattr(candidate_module.LineageStore, "add", fail_lineage_add)

    with pytest.raises(OSError, match="lineage store failed"):
        PortraitPlugin().build(ctx, job.manifest)

    with pytest.raises(FileNotFoundError):
        LineageStore(data_root).get(f"{job.id}-candidate")
    assert JobStore(data_root).load(job.id).state.value == "processing"
    assert [event.message for event in EventLog(data_root).read(job.id)] == [
        "created->planning",
        "planning->processing",
    ]
    assert not (ctx.workspace / "candidate").exists()


def test_build_reports_provider_failure_without_falsely_claiming_missing_artifacts(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-provider-fail"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            return GenResponse(
                ok=False,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="4" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is False
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_FAILED"}
    assert JobStore(data_root).load(job.id).state.value == "failed"


def test_build_appends_error_when_failed_provider_only_reports_warning(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    provider_diag = warning("PROVIDER_NOTE", "provider warning without success")

    class _Provider:
        id = "stub-provider-warning-fail"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            return GenResponse(ok=False, diagnostics=(provider_diag,))

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is False
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_FAILED", "PROVIDER_NOTE"}
    assert JobStore(data_root).load(job.id).state.value == "failed"


def test_build_returns_structured_failure_for_invalid_neutral_artifact_path(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-invalid-path"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="../escape.png",
                        sha256="5" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is False
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_INVALID_RESPONSE"}
    assert JobStore(data_root).load(job.id).state.value == "failed"


def test_build_returns_structured_failure_for_provider_refusal(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-provider-refusal"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            raise ProviderRefusal("provider refused request")

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is False
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_FAILED"}
    assert JobStore(data_root).load(job.id).state.value == "failed"


def test_build_marks_job_failed_on_unexpected_provider_exception(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-provider-crash"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            raise RuntimeError("provider crash")

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())

    with pytest.raises(RuntimeError, match="provider crash"):
        PortraitPlugin().build(ctx, job.manifest)

    assert JobStore(data_root).load(job.id).state.value == "failed"


def test_repeated_build_preserves_review_job_state_and_history(data_root: Path) -> None:
    import fecreator.providers  # noqa: F401
    from fecreator.assets.portrait.plugin import PortraitPlugin

    plugin = PortraitPlugin()
    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)

    first_result = plugin.build(ctx, job.manifest)
    events_before = [event.message for event in EventLog(data_root).read(job.id)]
    stored_before = JobStore(data_root).load(job.id)
    candidate_before = (ctx.workspace / "candidate" / "candidate.json").read_bytes()
    package_before = (ctx.workspace / "candidate" / "package" / "hero.png").read_bytes()
    lineage_before = LineageStore(data_root).get(f"{job.id}-candidate")

    assert first_result.ok is True
    with pytest.raises(InvalidTransitionError, match="waiting_for_review -> processing"):
        plugin.build(ctx, job.manifest)

    stored_after = JobStore(data_root).load(job.id)
    assert stored_after.state.value == "waiting_for_review"
    assert stored_after.revision == stored_before.revision
    assert [event.message for event in EventLog(data_root).read(job.id)] == events_before
    assert (ctx.workspace / "candidate" / "candidate.json").read_bytes() == candidate_before
    assert (ctx.workspace / "candidate" / "package" / "hero.png").read_bytes() == package_before
    assert LineageStore(data_root).get(f"{job.id}-candidate") == lineage_before


def test_concurrent_build_serializes_candidate_creation(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    provider_started = threading.Event()
    allow_first_provider_call = threading.Event()
    calls_lock = threading.Lock()
    provider_calls = 0

    class _BlockingProvider:
        id = "blocking-provider"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            nonlocal provider_calls
            del request
            with calls_lock:
                provider_calls += 1
                call_number = provider_calls
            if call_number == 1:
                provider_started.set()
                assert allow_first_provider_call.wait(timeout=5)
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="8" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _BlockingProvider()
    )
    plugin = PortraitPlugin()
    results = []
    errors = []

    def build() -> None:
        try:
            results.append(plugin.build(ctx, job.manifest))
        except Exception as exc:
            errors.append(exc)

    first = threading.Thread(target=build)
    second = threading.Thread(target=build)
    first.start()
    assert provider_started.wait(timeout=5)
    second.start()
    time.sleep(0.1)
    with calls_lock:
        assert provider_calls == 1
    allow_first_provider_call.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(results) == 1
    assert results[0].ok is True
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidTransitionError)
    assert JobStore(data_root).load(job.id).state is JobState.WAITING_FOR_REVIEW
    assert (ctx.workspace / "candidate" / "candidate.json").exists()
    assert LineageStore(data_root).get(f"{job.id}-candidate").asset_id == f"{job.id}-candidate"


def test_concurrent_build_cannot_process_while_first_build_is_failing(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    provider_started = threading.Event()
    allow_provider_failure = threading.Event()
    failure_finalization_started = threading.Event()
    allow_failure_finalization = threading.Event()
    second_provider_started = threading.Event()
    provider_calls = 0
    provider_calls_lock = threading.Lock()

    class _FailingProvider:
        id = "failing-provider"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            nonlocal provider_calls
            del request, workspace
            with provider_calls_lock:
                provider_calls += 1
                call_number = provider_calls
            if call_number == 1:
                provider_started.set()
                assert allow_provider_failure.wait(timeout=5)
                raise RuntimeError("provider crash")
            second_provider_started.set()
            raise AssertionError("second build reached provider while failure was finalizing")

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _FailingProvider()
    )
    plugin = PortraitPlugin()
    original_mark_failed = plugin._mark_job_failed_if_possible

    def pause_failure_finalization(data_root: Path, job_id: str, *, job_locked: bool = False):
        failure_finalization_started.set()
        assert allow_failure_finalization.wait(timeout=5)
        return original_mark_failed(data_root, job_id, job_locked=job_locked)

    monkeypatch.setattr(plugin, "_mark_job_failed_if_possible", pause_failure_finalization)
    errors = []

    def build() -> None:
        try:
            plugin.build(ctx, job.manifest)
        except Exception as exc:
            errors.append(exc)

    first = threading.Thread(target=build)
    second = threading.Thread(target=build)
    first.start()
    assert provider_started.wait(timeout=5)
    second.start()
    allow_provider_failure.set()
    assert failure_finalization_started.wait(timeout=5)
    assert not second_provider_started.wait(timeout=0.1)
    allow_failure_finalization.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(errors) == 2
    assert all(isinstance(exc, (InvalidTransitionError, RuntimeError)) for exc in errors)
    assert JobStore(data_root).load(job.id).state is JobState.FAILED


def test_build_surfaces_candidate_rollback_cleanup_failure(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.candidate as candidate_module
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "rollback-cleanup-provider"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request
            save_png(workspace / "generated" / "neutral.png", _portrait_rgb())
            return GenResponse(
                ok=True,
                artifacts=(
                    Artifact(
                        role="neutral",
                        path="generated/neutral.png",
                        sha256="9" * 64,
                        media_type="image/png",
                    ),
                ),
            )

    original_append_many = plugin_module.EventLog.append_many
    original_unlink = candidate_module.os.unlink

    def fail_review_transition(self, job_id: str, events):
        if any(
            kind == "transition" and message == "processing->waiting_for_review"
            for kind, message, _ in events
        ):
            raise OSError("transition event failed")
        return original_append_many(self, job_id, events)

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)

    def fail_snapshot_removal(path, *args, **kwargs):
        if Path(path).name == "candidate.json":
            raise PermissionError("candidate deletion denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())
    monkeypatch.setattr(plugin_module.EventLog, "append_many", fail_review_transition)
    monkeypatch.setattr(candidate_module.os, "unlink", fail_snapshot_removal)

    with pytest.raises(PermissionError, match="candidate deletion denied") as raised:
        PortraitPlugin().build(ctx, job.manifest)

    assert isinstance(raised.value.__cause__, OSError)
    assert str(raised.value.__cause__) == "transition event failed"
    assert (ctx.workspace / "candidate" / "candidate.json").exists()


def test_build_from_cancelled_job_preserves_cancelled_state_and_history(data_root: Path) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    job = JobStore(data_root).create(_manifest())
    JobService(JobStore(data_root), EventLog(data_root)).cancel(job.id)
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    events_before = [event.message for event in EventLog(data_root).read(job.id)]

    with pytest.raises(InvalidTransitionError, match="cancelled -> processing"):
        PortraitPlugin().build(ctx, job.manifest)

    stored_job = JobStore(data_root).load(job.id)
    assert stored_job.state.value == "cancelled"
    assert [event.message for event in EventLog(data_root).read(job.id)] == events_before


def test_app_end_to_end(data_root: Path, isolated_app_asset_bootstrap: None) -> None:
    from fecreator.core.config import Settings

    app_module = importlib.import_module("fecreator.app")
    app = app_module.FeCreatorApp(Settings(data_root=data_root))

    assert "portrait" in app.list_assets()
    assert "fake" in app.list_providers()
    assert "fe-gba-portrait-standard" in app.list_specs()

    job = app.create_job(_manifest())
    result = app.build(job.id)
    package_dir = data_root / "jobs" / job.id / "candidate" / "package"

    assert result.ok is True
    assert result.lineage_id == f"{job.id}-candidate"
    assert not has_errors(app.validate("fe-gba-portrait-standard", package_dir))
    assert app.get_job(job.id).state.value == "waiting_for_review"
    assert app.get_job_candidate(job.id).lineage_id == f"{job.id}-candidate"
    assert LineageStore(data_root).get(f"{job.id}-candidate").asset_id == f"{job.id}-candidate"
    assert not (data_root / "jobs" / job.id / "package").exists()
    assert not (data_root / "jobs" / job.id / "report.json").exists()
    assert not (data_root / "jobs" / job.id / "lineage.json").exists()
    assert not (data_root / "jobs" / job.id / "bundle").exists()
