from __future__ import annotations

from typing import cast

from fecreator.assets.base import SourcePlan, SubmissionSchema
from fecreator.assets.portrait.references import reference_roles
from fecreator.contracts.manifest import AssetMetadata, Manifest
from fecreator.references.model import ReferencePack


def build_prompt(manifest: Manifest, pack: ReferencePack | None) -> str:
    text = " ".join(source.ref for source in manifest.sources if source.kind == "text")
    subject = text or cast(AssetMetadata, manifest.metadata).purpose
    forbidden = (
        f"; preserve: {', '.join(pack.forbidden_changes)}"
        if pack and pack.forbidden_changes
        else ""
    )
    return (
        f"{subject}{forbidden}; Fire Emblem 8 dialogue background source; "
        "240x160 composition; no text, logos, portrait frames, or characters; "
        "keep critical focal detail out of the lower 48 pixels"
    )


def plan_sources(manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
    metadata = cast(AssetMetadata, manifest.metadata)
    return SourcePlan(
        prompts=(build_prompt(manifest, pack),),
        reference_roles=reference_roles(pack) if pack else {},
        expected_filenames=(f"{metadata.name}.png",),
        required_expressions=(),
        background_contract="one opaque 240x160 RGB or indexed PNG",
        forbidden_colors=(),
        submission_schema=SubmissionSchema(
            forbidden_changes=pack.forbidden_changes if pack else (),
            canonical_swatches=pack.swatches if pack else (),
            traits=dict(pack.traits) if pack else {},
            provenance=metadata.source_note,
            rights=metadata.license_note,
            files=f"one opaque 240x160 PNG named {metadata.name}.png",
        ),
    )
