"""Build must not hold the job lock while a provider runs.

The provider call is the one unbounded step in a build. Holding the shared job
lock across it makes every ordinary read (HTTP, CLI, MCP, WebSocket) wait for
the sidecar lock and then fail as an unstructured timeout. These tests pin the
short-transition design: claim ``processing`` under the lock, release it, run
the provider, and reacquire only to publish or fail.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.pipeline import PipelineContext
from fecreator.jobs.events import EventLog
from fecreator.jobs.model import JobState
from fecreator.jobs.service import InvalidTransitionError, JobService
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.providers.base import GenRequest, GenResponse
from tests.portrait.test_build_e2e import _portrait_rgb

_READ_BUDGET_SECONDS = 1.0


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight"),),
    )


class _GateProvider:
    """Provider that blocks until the test releases it."""

    id = "gate-provider"
    capabilities = CapabilitySet(capabilities=frozenset(Capability))

    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        self._started = started
        self._release = release
        self.calls = 0
        self._calls_lock = threading.Lock()

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        from fecreator.imaging.io import save_png

        del request
        with self._calls_lock:
            self.calls += 1
        self._started.set()
        assert self._release.wait(timeout=10)
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


def _start_gated_build(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[threading.Thread, _GateProvider, threading.Event, list[object], str]:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    started = threading.Event()
    release = threading.Event()
    provider = _GateProvider(started, release)
    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: provider)
    outcomes: list[object] = []

    def run_build() -> None:
        try:
            outcomes.append(PortraitPlugin().build(ctx, job.manifest))
        except Exception as exc:  # noqa: BLE001 - recorded for assertions
            outcomes.append(exc)

    thread = threading.Thread(target=run_build)
    thread.start()
    assert started.wait(timeout=10)
    return thread, provider, release, outcomes, job.id


def test_job_reads_stay_responsive_while_the_provider_is_running(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread, _provider, release, outcomes, job_id = _start_gated_build(data_root, monkeypatch)
    try:
        started_at = time.monotonic()
        job = JobStore(data_root).load(job_id)
        events = EventLog(data_root).read(job_id)
        elapsed = time.monotonic() - started_at

        assert job.state is JobState.PROCESSING
        assert [event.message for event in events] == [
            "created->planning",
            "planning->processing",
        ]
        assert elapsed < _READ_BUDGET_SECONDS
    finally:
        release.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(outcomes) == 1
    assert getattr(outcomes[0], "ok", None) is True


def test_second_build_fails_explicitly_while_the_first_provider_is_running(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    thread, provider, release, outcomes, job_id = _start_gated_build(data_root, monkeypatch)
    ctx = PipelineContext(job_id=job_id, workspace=data_root / "jobs" / job_id)
    manifest = JobStore(data_root).load(job_id).manifest
    try:
        started_at = time.monotonic()
        with pytest.raises(InvalidTransitionError, match="processing -> processing"):
            PortraitPlugin().build(ctx, manifest)
        elapsed = time.monotonic() - started_at

        assert elapsed < _READ_BUDGET_SECONDS
        assert provider.calls == 1
    finally:
        release.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(outcomes) == 1
    assert getattr(outcomes[0], "ok", None) is True
    assert JobStore(data_root).load(job_id).state is JobState.WAITING_FOR_REVIEW
    assert LineageStore(data_root).get(f"{job_id}-candidate").asset_id == f"{job_id}-candidate"
    assert provider.calls == 1


def test_a_failed_claim_marks_the_job_failed_without_reaching_the_provider(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolving the pack and provider happens inside the claim, and still fails loudly."""
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    calls: list[str] = []

    class _NeverCalledProvider:
        id = "never-called"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            calls.append("generate")
            raise AssertionError("provider must not run when the claim fails")

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _NeverCalledProvider()
    )
    monkeypatch.setattr(
        PortraitPlugin,
        "_reference_pack",
        lambda self, data_root, manifest: (_ for _ in ()).throw(OSError("reference store down")),
    )

    with pytest.raises(OSError, match="reference store down"):
        PortraitPlugin().build(ctx, job.manifest)

    assert calls == []
    assert JobStore(data_root).load(job.id).state is JobState.FAILED


def test_an_interrupted_build_can_be_rebuilt_from_processing(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stranded `processing` job must stay reachable once no build holds the lease."""
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    JobService(JobStore(data_root), EventLog(data_root)).transition_path(
        job.id, (JobState.PLANNING, JobState.PROCESSING)
    )
    provider = _GateProvider(threading.Event(), threading.Event())
    provider._release.set()
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: provider)

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    assert JobStore(data_root).load(job.id).state is JobState.WAITING_FOR_REVIEW


def test_cancelling_during_the_provider_run_still_reports_build_diagnostics(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal discovered after a concurrent cancel must not become an opaque error."""
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin
    from fecreator.providers.base import ProviderRefusal

    class _RefusingProvider:
        id = "refusing-provider"
        capabilities = CapabilitySet(capabilities=frozenset(Capability))

        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            del request, workspace
            JobService(JobStore(data_root), EventLog(data_root)).cancel(job.id)
            raise ProviderRefusal("missing capability")

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _RefusingProvider()
    )

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is False
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["PROVIDER_FAILED"]
    assert JobStore(data_root).load(job.id).state is JobState.CANCELLED


def test_a_refused_publication_leaves_no_staged_candidate_behind(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _CancellingProvider(_GateProvider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            response = super().generate(request, workspace)
            JobService(JobStore(data_root), EventLog(data_root)).cancel(job.id)
            return response

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    release = threading.Event()
    release.set()
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY,
        "get",
        lambda provider_id: _CancellingProvider(threading.Event(), release),
    )

    with pytest.raises(InvalidTransitionError, match="cancelled -> processing"):
        PortraitPlugin().build(ctx, job.manifest)

    staged = [entry.name for entry in ctx.workspace.iterdir() if entry.name.startswith(".")]
    assert staged == []
    assert not (ctx.workspace / "candidate").exists()
    assert JobStore(data_root).load(job.id).state is JobState.CANCELLED


def test_a_contended_job_lock_at_publish_is_reported_as_lock_contention(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A body ``LockTimeoutError`` must not be relabelled as a second build.

    The lease only proves that no *other* build is in flight. Contention on the
    job lock during the short claim or publish transitions is a different
    failure, and every adapter maps it to ``STORE_LOCK_TIMEOUT``.
    """
    import fecreator.assets.portrait.plugin as plugin_module
    import fecreator.assets.reviewed as reviewed_module
    from fecreator.assets.portrait.plugin import PortraitPlugin
    from fecreator.core.atomicio import LockTimeoutError

    provider_finished = threading.Event()
    job = JobStore(data_root).create(_manifest())
    lock_path = data_root / "jobs" / job.id / "job.json"
    message = f"timed out acquiring lock for {lock_path} via {lock_path}.lock"

    class _ContendedStore(JobStore):
        def locked(self, job_id: str):  # type: ignore[no-untyped-def]
            if provider_finished.is_set():
                raise LockTimeoutError(message)
            return super().locked(job_id)

    class _SignallingProvider(_GateProvider):
        def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
            response = super().generate(request, workspace)
            provider_finished.set()
            return response

    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    release = threading.Event()
    release.set()
    monkeypatch.setattr(reviewed_module, "JobStore", _ContendedStore)
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY,
        "get",
        lambda provider_id: _SignallingProvider(threading.Event(), release),
    )

    with pytest.raises(LockTimeoutError):
        PortraitPlugin().build(ctx, job.manifest)

    assert [entry.name for entry in ctx.workspace.iterdir() if entry.name.startswith(".")] == []
    assert not (ctx.workspace / "candidate").exists()
    assert JobStore(data_root).load(job.id).state is JobState.PROCESSING


def test_a_contended_job_lock_at_claim_is_reported_as_lock_contention(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contention before the provider runs is contention, not a duplicate build."""
    import fecreator.assets.portrait.plugin as plugin_module
    import fecreator.assets.reviewed as reviewed_module
    from fecreator.assets.portrait.plugin import PortraitPlugin
    from fecreator.core.atomicio import LockTimeoutError

    job = JobStore(data_root).create(_manifest())
    lock_path = data_root / "jobs" / job.id / "job.json"

    class _ContendedStore(JobStore):
        def locked(self, job_id: str):  # type: ignore[no-untyped-def]
            raise LockTimeoutError(f"timed out acquiring lock for {lock_path}")

    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    provider = _GateProvider(threading.Event(), threading.Event())
    provider._release.set()
    monkeypatch.setattr(reviewed_module, "JobStore", _ContendedStore)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: provider)

    with pytest.raises(LockTimeoutError):
        PortraitPlugin().build(ctx, job.manifest)

    assert provider.calls == 0


def test_build_leases_are_not_shared_by_dotted_job_ids(data_root: Path) -> None:
    """`hero.v2` and `hero` are different jobs and must hold different leases."""
    from fecreator.assets.portrait.plugin import PortraitPlugin

    plugin = PortraitPlugin()

    with plugin._build_lease(data_root, "hero.v2"), plugin._build_lease(data_root, "hero"):
        pass

    lease_files = sorted(path.name for path in (data_root / "jobs" / ".locks").iterdir())
    assert lease_files == ["build-hero.lock", "build-hero.v2.lock"]


def test_a_second_build_of_the_same_job_still_contends_on_the_lease(data_root: Path) -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    plugin = PortraitPlugin()

    def take_second_lease() -> None:
        with plugin._build_lease(data_root, "hero"):
            raise AssertionError("a second lease must never be granted")

    with (
        plugin._build_lease(data_root, "hero"),
        pytest.raises(InvalidTransitionError, match="a build is already running"),
    ):
        take_second_lease()
