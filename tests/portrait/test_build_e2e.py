from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import has_errors, warning
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.pipeline import PipelineContext
from fecreator.imaging.io import save_png
from fecreator.jobs.events import EventLog
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight"),),
    )


def _portrait_rgb() -> np.ndarray:
    rgb = np.full((80, 96, 3), (0, 248, 0), dtype=np.uint8)
    rgb[20:60, 20:60] = (200, 40, 40)
    return rgb


def _background_rgb() -> np.ndarray:
    return np.full((80, 96, 3), (0, 248, 0), dtype=np.uint8)


def test_plugin_required_caps() -> None:
    from fecreator.assets.portrait.plugin import PortraitPlugin

    assert PortraitPlugin().required_capabilities("text_to_portrait") == {Capability.TEXT_TO_IMAGE}


def test_build_produces_valid_package_and_lineage(data_root: Path) -> None:
    import fecreator.providers  # noqa: F401
    from fecreator.assets.portrait.plugin import PortraitPlugin

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    assert result.lineage_id == job.id
    package = ctx.workspace / "package"
    assert not has_errors(FeGbaPortraitStandard().validate(package))
    assert LineageStore(data_root).get(job.id).operation.value == "export_spec"
    assert (ctx.workspace / "report.json").exists()
    assert (ctx.workspace / "lineage.json").exists()
    assert (ctx.workspace / "bundle" / "manifest.json").exists()


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
    assert not has_errors(FeGbaPortraitStandard().validate(ctx.workspace / "package"))


def test_build_carries_provider_diagnostics_and_completed_report_state(
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
    report = json.loads((ctx.workspace / "report.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert {diag.code for diag in result.diagnostics} == {"PROVIDER_NOTE"}
    assert JobStore(data_root).load(job.id).state.value == "completed"
    assert [event.message for event in EventLog(data_root).read(job.id)] == [
        "created->planning",
        "planning->processing",
        "processing->validating",
        "validating->completed",
    ]
    assert report["state"] == "completed"
    assert {diag["code"] for diag in report["diagnostics"]} == {"PROVIDER_NOTE"}


def test_build_does_not_persist_lineage_when_bundle_fails(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    class _Provider:
        id = "stub-bundle-fail"
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

    job = JobStore(data_root).create(_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    monkeypatch.setattr(plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _Provider())
    monkeypatch.setattr(
        plugin_module,
        "build_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("bundle failed")),
    )

    with pytest.raises(OSError, match="bundle failed"):
        PortraitPlugin().build(ctx, job.manifest)

    with pytest.raises(FileNotFoundError):
        LineageStore(data_root).get(job.id)


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
