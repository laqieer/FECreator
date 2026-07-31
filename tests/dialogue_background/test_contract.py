from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)


def _package_manifest() -> DialogueBackgroundPackageManifest:
    return DialogueBackgroundPackageManifest(
        name="phantom_city",
        purpose="Original phantom-city dialogue background",
        provider="manual",
        prompt="A ghostly imperial city at twilight",
        source=DialogueBackgroundSourceRecord(
            kind="prompt",
            id="dialogue-background/phantom-city",
            revision="1",
            input_sha256="a" * 64,
        ),
        png_sha256="b" * 64,
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
        requested_downstream_profile="fe8-dialogue-background-feimg2",
    )


def test_package_manifest_pins_normative_contract() -> None:
    manifest = _package_manifest()

    assert manifest.version == "1.0"
    assert manifest.contract_version == "1.0"
    assert manifest.asset_type == "dialogue_background"
    assert manifest.target_spec == "fe8-dialogue-background-source-240x160"
    assert (manifest.width, manifest.height, manifest.opaque) == (240, 160, True)


def test_package_manifest_rejects_reference_revision_without_pack() -> None:
    payload = _package_manifest().model_dump(mode="python")
    payload["reference_pack"] = None
    payload["reference_pack_rev"] = 1

    with pytest.raises(ValidationError, match="reference_pack and reference_pack_rev"):
        DialogueBackgroundPackageManifest.model_validate(payload)


@pytest.mark.parametrize("revision", [0, -1])
def test_package_manifest_rejects_non_positive_reference_revisions(revision: int) -> None:
    payload = _package_manifest().model_dump(mode="python")
    payload["reference_pack"] = "reference-pack"
    payload["reference_pack_rev"] = revision

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        DialogueBackgroundPackageManifest.model_validate(payload)


@pytest.mark.parametrize("field", ["input_sha256", "png_sha256"])
def test_package_manifest_rejects_invalid_hashes(field: str) -> None:
    payload = _package_manifest().model_dump(mode="python")
    if field == "input_sha256":
        payload["source"]["input_sha256"] = "not-a-hash"
    else:
        payload[field] = "not-a-hash"

    with pytest.raises(ValidationError):
        DialogueBackgroundPackageManifest.model_validate(payload)
