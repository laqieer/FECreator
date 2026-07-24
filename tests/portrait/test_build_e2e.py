from __future__ import annotations

from pathlib import Path

from fecreator.contracts.capabilities import Capability
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.pipeline import PipelineContext
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight"),),
    )


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
