from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.lineage import Region
from fecreator.contracts.manifest import (
    AssetMetadata,
    EditSpec,
    Manifest,
    SourceIdentity,
    SourceSpec,
)


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight"),),
    )


def _background_metadata() -> AssetMetadata:
    return AssetMetadata(
        name="phantom_city",
        purpose="Original phantom-city dialogue background",
        source=SourceIdentity(
            kind="prompt",
            id="dialogue-background/phantom-city",
            revision="1",
        ),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
        requested_downstream_profile="fe8-dialogue-background-feimg2",
    )


def test_manifest_defaults_and_hash_stable() -> None:
    manifest = _manifest()

    assert manifest.version == "1.0"
    assert manifest.content_hash() == _manifest().content_hash()
    assert len(manifest.content_hash()) == 64


def test_manifest_is_frozen() -> None:
    manifest = _manifest()

    with pytest.raises((ValidationError, TypeError)):
        manifest.provider = "manual"


def test_manifest_params_are_immutable() -> None:
    manifest = Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        params={"seed": 7},
    )

    with pytest.raises(TypeError):
        manifest.params["seed"] = 8


def test_edit_spec_regions() -> None:
    edit = EditSpec(
        mask_path="mask.png",
        protected_regions=(Region(x=0, y=0, w=96, h=80, label="face"),),
    )

    assert edit.protected_regions[0].label == "face"


def test_invalid_source_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        SourceSpec(kind="video", ref="x")


def test_dialogue_background_manifest_accepts_normative_identifiers() -> None:
    manifest = Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow="text_to_dialogue_background",
        provider="fake",
        metadata=_background_metadata(),
        sources=(SourceSpec(kind="text", ref="phantom city"),),
    )

    assert manifest.metadata == _background_metadata()


@pytest.mark.parametrize(
    ("asset_type", "target_spec", "workflow"),
    [
        ("dialogue_background", "fe-gba-portrait-standard", "text_to_dialogue_background"),
        ("portrait", "fe8-dialogue-background-source-240x160", "text_to_portrait"),
        ("dialogue_background", "fe8-dialogue-background-source-240x160", "text_to_portrait"),
    ],
)
def test_manifest_rejects_cross_asset_contracts(
    asset_type: str,
    target_spec: str,
    workflow: str,
) -> None:
    with pytest.raises(ValidationError):
        Manifest(
            asset_type=asset_type,
            target_spec=target_spec,
            workflow=workflow,
            provider="fake",
            metadata=_background_metadata() if asset_type == "dialogue_background" else None,
        )


def test_dialogue_background_requires_metadata() -> None:
    with pytest.raises(ValidationError, match="metadata"):
        Manifest(
            asset_type="dialogue_background",
            target_spec="fe8-dialogue-background-source-240x160",
            workflow="text_to_dialogue_background",
            provider="fake",
        )


def test_portrait_rejects_dialogue_background_metadata() -> None:
    payload = _manifest().model_dump(mode="python")
    payload["metadata"] = _background_metadata().model_dump(mode="python")

    with pytest.raises(ValidationError, match="metadata"):
        Manifest.model_validate(payload)


def test_edit_only_valid_for_masked_variant() -> None:
    with pytest.raises(ValidationError):
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            edit=EditSpec(mask_path="m.png"),
        )


def test_edit_is_allowed_for_masked_variant() -> None:
    manifest = Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="masked_variant",
        provider="fake",
        parent_asset_id="hero-candidate",
        edit=EditSpec(mask_path="m.png"),
    )

    assert manifest.edit is not None


@pytest.mark.parametrize("workflow", ["expression_refine", "masked_variant"])
def test_approved_base_workflows_require_a_parent_asset_id(workflow: str) -> None:
    with pytest.raises(ValidationError, match="parent_asset_id"):
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow=workflow,
            provider="fake",
            sources=(SourceSpec(kind="approved_portrait", ref="hero.png"),),
            edit=EditSpec(mask_path="m.png") if workflow == "masked_variant" else None,
        )


@pytest.mark.parametrize("workflow", ["expression_refine", "masked_variant"])
def test_approved_base_workflows_reject_a_blank_parent_asset_id(workflow: str) -> None:
    with pytest.raises(ValidationError, match="parent_asset_id"):
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow=workflow,
            provider="fake",
            parent_asset_id="   ",
            sources=(SourceSpec(kind="approved_portrait", ref="hero.png"),),
            edit=EditSpec(mask_path="m.png") if workflow == "masked_variant" else None,
        )


@pytest.mark.parametrize("workflow", ["text_to_portrait", "concept_to_portrait"])
def test_originating_workflows_reject_a_parent_asset_id(workflow: str) -> None:
    with pytest.raises(ValidationError, match="parent_asset_id"):
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow=workflow,
            provider="fake",
            parent_asset_id="hero-candidate",
        )


def test_parent_asset_id_is_normalized_and_defaults_to_none() -> None:
    manifest = Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="expression_refine",
        provider="fake",
        parent_asset_id="  hero-candidate  ",
        sources=(SourceSpec(kind="approved_portrait", ref="hero.png"),),
    )

    assert manifest.parent_asset_id == "hero-candidate"
    assert _manifest().parent_asset_id is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "2.0"),
        ("asset_type", "sprite"),
        ("target_spec", "other-spec"),
        ("workflow", "freeform"),
    ],
)
def test_invalid_v1_identifiers_are_rejected(field: str, value: str) -> None:
    payload = _manifest().model_dump(mode="python")
    payload[field] = value

    with pytest.raises(ValidationError):
        Manifest(**payload)


def test_manifest_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Manifest(
            asset_type="portrait",
            target_spec="fe-gba-portrait-standard",
            workflow="text_to_portrait",
            provider="fake",
            unexpected="value",
        )


def test_reference_revision_requires_pack_id() -> None:
    payload = _manifest().model_dump(mode="python")
    payload["character_ref_pack_rev"] = 2

    with pytest.raises(ValidationError, match="character_ref_pack_rev"):
        Manifest.model_validate(payload)
