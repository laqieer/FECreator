from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import cast

from fecreator.assets.candidate import CandidatePublication, _remove_tree
from fecreator.assets.dialogue_background.workflows import PreparedDialogueBackground
from fecreator.assets.reviewed import CandidateValidationError
from fecreator.contracts.diagnostics import has_errors
from fecreator.contracts.dialogue_background import (
    DialogueBackgroundPackageManifest,
    DialogueBackgroundSourceRecord,
)
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import AssetMetadata, Manifest
from fecreator.contracts.result import Artifact
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import write_json_atomic
from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import sha256_bytes, sha256_file
from fecreator.core.paths import safe_join
from fecreator.core.pipeline import PipelineContext
from fecreator.imaging.io import save_canonical_rgb_png
from fecreator.references.model import ReferencePack
from fecreator.specs.fire_emblem.gba.dialogue_background_source.spec import (
    Fe8DialogueBackgroundSource240x160,
)

_CANDIDATE_STAGE_PREFIX = ".candidate-stage-"


def prepare_candidate(
    *,
    ctx: PipelineContext,
    manifest: Manifest,
    prepared: PreparedDialogueBackground,
    reference_pack: ReferencePack | None,
    parent_candidate_id: str | None = None,
) -> CandidatePublication:
    staged_root = safe_join(ctx.workspace, f"{_CANDIDATE_STAGE_PREFIX}{uuid.uuid4().hex}")
    package_dir = safe_join(staged_root, "package")
    try:
        metadata = cast(AssetMetadata, manifest.metadata)
        package_dir.mkdir(parents=True, exist_ok=False)
        png_path = safe_join(package_dir, f"{metadata.name}.png")
        save_canonical_rgb_png(png_path, prepared.rgb)
        package_manifest = DialogueBackgroundPackageManifest(
            name=metadata.name,
            purpose=metadata.purpose,
            provider=manifest.provider,
            model=prepared.provider_model,
            prompt=prepared.prompt,
            reference_pack=reference_pack.id if reference_pack else None,
            reference_pack_rev=reference_pack.revision if reference_pack else None,
            source=DialogueBackgroundSourceRecord(
                kind=metadata.source.kind,
                id=metadata.source.id,
                revision=metadata.source.revision,
                input_sha256=_input_hash(manifest, prepared.inputs),
            ),
            png_sha256=sha256_file(png_path),
            license_note=metadata.license_note,
            source_note=metadata.source_note,
            requested_downstream_profile=metadata.requested_downstream_profile,
        )
        manifest_path = safe_join(package_dir, f"{metadata.name}.manifest.json")
        write_json_atomic(manifest_path, package_manifest.model_dump(mode="json"))
        manifest_path.with_suffix(f"{manifest_path.suffix}.lock").unlink()
        diagnostics = tuple(Fe8DialogueBackgroundSource240x160().validate(package_dir))
        if has_errors(diagnostics):
            raise CandidateValidationError(diagnostics)
        artifacts = _candidate_artifacts(package_dir, metadata.name)
        lineage = _candidate_lineage(
            ctx.job_id,
            manifest,
            prepared,
            reference_pack,
            artifacts,
            parent_candidate_id,
        )
        snapshot = CandidateSnapshot(
            job_id=ctx.job_id,
            lineage_id=lineage.asset_id,
            artifacts=artifacts,
            diagnostics=prepared.diagnostics + diagnostics,
            metrics=prepared.metrics,
            created_at=lineage.created_at,
        )
        return CandidatePublication(snapshot, lineage, staged_root)
    except Exception as exc:
        try:
            _remove_tree(staged_root)
        except Exception as cleanup_exc:
            raise cleanup_exc from exc
        raise


def _input_hash(manifest: Manifest, inputs: tuple[Artifact, ...]) -> str:
    payload = {
        "manifest": manifest.model_dump(mode="json"),
        "inputs": [
            artifact.model_dump(mode="json")
            for artifact in sorted(
                inputs,
                key=lambda item: (item.role, item.path, item.sha256, item.media_type),
            )
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


def _candidate_artifacts(package_dir: Path, name: str) -> tuple[Artifact, ...]:
    png = safe_join(package_dir, f"{name}.png")
    package_manifest = safe_join(package_dir, f"{name}.manifest.json")
    return (
        Artifact(
            role="background",
            path=f"candidate/package/{name}.png",
            sha256=sha256_file(png),
            media_type="image/png",
        ),
        Artifact(
            role="manifest",
            path=f"candidate/package/{name}.manifest.json",
            sha256=sha256_file(package_manifest),
            media_type="application/json",
        ),
    )


def _candidate_lineage(
    job_id: str,
    manifest: Manifest,
    prepared: PreparedDialogueBackground,
    reference_pack: ReferencePack | None,
    artifacts: tuple[Artifact, ...],
    parent_candidate_id: str | None,
) -> LineageNode:
    parents = prepared.parents
    if parent_candidate_id is not None and parent_candidate_id not in parents:
        parents = (*parents, parent_candidate_id)
    return LineageNode(
        asset_id=f"{job_id}-candidate",
        operation=prepared.operation,
        parents=parents,
        provider=manifest.provider,
        model=prepared.provider_model,
        prompt=prepared.prompt,
        reference_pack=reference_pack.id if reference_pack else None,
        reference_pack_rev=reference_pack.revision if reference_pack else None,
        seed=prepared.seed,
        params=manifest.params,
        mask=prepared.mask,
        protected_regions=prepared.protected_regions,
        metrics=prepared.metrics,
        output_hashes=tuple(sorted(artifact.sha256 for artifact in artifacts)),
        created_at=utc_now_iso(),
    )
