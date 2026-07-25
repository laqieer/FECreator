from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.lineage import Region
from fecreator.contracts.manifest import EditSpec, Manifest, SourceSpec


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight"),),
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
        edit=EditSpec(mask_path="m.png"),
    )

    assert manifest.edit is not None


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
