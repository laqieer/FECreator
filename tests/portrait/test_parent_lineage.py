"""Expression and masked builds must record their approved base as a parent.

The approved design says a refined or masked candidate is derived from an
approved portrait, so the lineage graph has to carry that edge. ``Manifest``
gained ``parent_asset_id`` for exactly this, and the workflows must promote it
into ``PreparedPortrait.parents`` so the persisted ``LineageNode`` names it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.lineage import LineageNode, Operation, Region
from fecreator.contracts.manifest import EditSpec, Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.pipeline import PipelineContext
from fecreator.imaging.io import save_png
from fecreator.jobs.store import JobStore
from fecreator.lineage.store import LineageStore
from fecreator.providers.base import GenRequest, GenResponse
from tests.portrait.test_build_e2e import _provider_colours, _write_multicolour_package

_BASE_ASSET_ID = "approved-hero-portrait"
_EXPRESSION_ROLES = ("half_closed_eyes", "closed_eyes", "mouth1", "mouth2", "mouth3")


class _ExpressionProvider:
    id = "expression-parent-provider"
    capabilities = CapabilitySet(capabilities=frozenset({Capability.IMAGE_TO_IMAGE}))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        del request
        artifacts = []
        for role in _EXPRESSION_ROLES:
            path = workspace / "generated" / f"{role}.png"
            save_png(path, _provider_colours(16, 32))
            artifacts.append(
                Artifact(
                    role=role,
                    path=f"generated/{role}.png",
                    sha256=sha256_file(path),
                    media_type="image/png",
                )
            )
        return GenResponse(ok=True, artifacts=tuple(artifacts), model="expression-model", seed=3)


class _MaskedProvider:
    id = "masked-parent-provider"
    capabilities = CapabilitySet(capabilities=frozenset({Capability.MASKED_EDIT}))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        del request
        path = workspace / "generated" / "variant.png"
        save_png(path, _provider_colours(80, 96))
        return GenResponse(
            ok=True,
            artifacts=(
                Artifact(
                    role="variant",
                    path="generated/variant.png",
                    sha256=sha256_file(path),
                    media_type="image/png",
                ),
            ),
            model="masked-model",
            seed=5,
        )


def _seed_approved_base(data_root: Path) -> None:
    LineageStore(data_root).add(
        LineageNode(
            asset_id=_BASE_ASSET_ID,
            operation=Operation.CREATE_NEUTRAL,
            created_at="2026-07-26T00:00:00+00:00",
        )
    )


def _expression_manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="expression_refine",
        provider="fake",
        parent_asset_id=_BASE_ASSET_ID,
        sources=(SourceSpec(kind="approved_portrait", ref="hero.png"),),
    )


def _masked_manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="masked_variant",
        provider="fake",
        parent_asset_id=_BASE_ASSET_ID,
        sources=(SourceSpec(kind="approved_portrait", ref="hero.png"),),
        edit=EditSpec(
            mask_path="mask.png",
            protected_regions=(Region(x=0, y=0, w=16, h=48, label="upper_left"),),
        ),
    )


def test_expression_refine_names_the_approved_base_as_a_lineage_parent(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    _seed_approved_base(data_root)
    job = JobStore(data_root).create(_expression_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    _write_multicolour_package(ctx.workspace / "submitted")
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _ExpressionProvider()
    )

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    node = LineageStore(data_root).get(f"{job.id}-candidate")
    assert node.parents == (_BASE_ASSET_ID,)
    ancestors = LineageStore(data_root).ancestors(f"{job.id}-candidate")
    assert [ancestor.asset_id for ancestor in ancestors] == [_BASE_ASSET_ID]


def test_masked_variant_names_the_approved_base_as_a_lineage_parent(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.assets.portrait.plugin import PortraitPlugin

    _seed_approved_base(data_root)
    job = JobStore(data_root).create(_masked_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    _write_multicolour_package(ctx.workspace / "submitted")
    mask = np.zeros((80, 96, 3), dtype=np.uint8)
    mask[48:64, 40:56] = 255
    save_png(ctx.workspace / "submitted" / "mask.png", mask)
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _MaskedProvider()
    )

    result = PortraitPlugin().build(ctx, job.manifest)

    assert result.ok is True
    node = LineageStore(data_root).get(f"{job.id}-candidate")
    assert node.parents == (_BASE_ASSET_ID,)


def test_app_exposes_the_approved_base_edge_through_lineage_ancestors(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.assets.portrait.plugin as plugin_module
    from fecreator.app import FeCreatorApp
    from fecreator.assets.portrait.plugin import PortraitPlugin
    from fecreator.core.config import Settings

    _seed_approved_base(data_root)
    job = JobStore(data_root).create(_expression_manifest())
    ctx = PipelineContext(job_id=job.id, workspace=data_root / "jobs" / job.id)
    _write_multicolour_package(ctx.workspace / "submitted")
    monkeypatch.setattr(
        plugin_module.PROVIDER_REGISTRY, "get", lambda provider_id: _ExpressionProvider()
    )
    PortraitPlugin().build(ctx, job.manifest)

    app = FeCreatorApp(Settings(data_root=data_root))
    ancestors = app.list_lineage_ancestors(f"{job.id}-candidate")

    assert [ancestor.asset_id for ancestor in ancestors] == [_BASE_ASSET_ID]
    assert app.list_lineage_children(_BASE_ASSET_ID)[0].asset_id == f"{job.id}-candidate"


def test_prepared_expression_and_masked_portraits_carry_the_parent(
    data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fecreator.assets.portrait.workflows import (
        prepare_expression_refine,
        prepare_masked_variant,
    )

    workspace = data_root / "jobs" / "prepare-only"
    _write_multicolour_package(workspace / "submitted")
    mask = np.zeros((80, 96, 3), dtype=np.uint8)
    mask[48:64, 40:56] = 255
    save_png(workspace / "submitted" / "mask.png", mask)
    del monkeypatch

    expression = prepare_expression_refine(
        _expression_manifest(), None, _ExpressionProvider(), workspace
    )
    masked = prepare_masked_variant(_masked_manifest(), None, _MaskedProvider(), workspace)

    assert expression.parents == (_BASE_ASSET_ID,)
    assert masked.parents == (_BASE_ASSET_ID,)
