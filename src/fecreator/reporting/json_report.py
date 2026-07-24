from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.result import StageResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.jobs.model import Job
from fecreator.reporting.sanitize import JsonObject, JsonValue, as_object, sanitize_json


def _stage_payload(result: StageResult) -> JsonObject:
    payload = as_object(sanitize_json(result.model_dump(mode="json"), error_cls=ValueError))
    artifacts = sorted(
        cast(list[JsonObject], payload["artifacts"]),
        key=lambda artifact: (
            cast(str, artifact["role"]),
            cast(str, artifact["path"]),
            cast(str, artifact["sha256"]),
        ),
    )
    diagnostics = sorted(
        cast(list[JsonObject], payload["diagnostics"]),
        key=lambda diagnostic: (
            cast(str, diagnostic["severity"]),
            cast(str, diagnostic["code"]),
            cast(str | None, diagnostic["where"]) or "",
            cast(str, diagnostic["message"]),
        ),
    )
    return {
        **payload,
        "artifacts": cast(JsonValue, artifacts),
        "diagnostics": cast(JsonValue, diagnostics),
    }


def _lineage_payload(node: LineageNode) -> JsonObject:
    payload = as_object(sanitize_json(node.model_dump(mode="json"), error_cls=ValueError))
    payload["output_hashes"] = cast(JsonValue, sorted(cast(list[str], payload["output_hashes"])))
    return payload


def build_report(
    job: Job, results: Sequence[StageResult], lineage: Sequence[LineageNode]
) -> JsonObject:
    manifest = as_object(sanitize_json(job.manifest.model_dump(mode="json"), error_cls=ValueError))
    stages = sorted(
        (_stage_payload(result) for result in results),
        key=lambda item: cast(str, item["stage"]),
    )
    lineage_payload = sorted(
        (_lineage_payload(node) for node in lineage),
        key=lambda item: (cast(str, item["created_at"]), cast(str, item["asset_id"])),
    )
    diagnostics = sorted(
        [
            diagnostic
            for stage in stages
            for diagnostic in cast(list[JsonObject], stage["diagnostics"])
        ],
        key=lambda item: (
            cast(str, item["severity"]),
            cast(str, item["code"]),
            cast(str | None, item["where"]) or "",
            cast(str, item["message"]),
        ),
    )
    output_hashes = sorted(
        {
            cast(str, artifact["sha256"])
            for stage in stages
            for artifact in cast(list[JsonObject], stage["artifacts"])
        }
        | {
            hash_value
            for node in lineage_payload
            for hash_value in cast(list[str], node["output_hashes"])
        }
    )
    return {
        "job_id": job.id,
        "state": job.state.value,
        "revision": job.revision,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "manifest": cast(JsonValue, manifest),
        "manifest_hash": job.manifest.content_hash(),
        "stages": cast(JsonValue, stages),
        "diagnostics": cast(JsonValue, diagnostics),
        "lineage": cast(JsonValue, lineage_payload),
        "output_hashes": cast(JsonValue, output_hashes),
    }


def write_report(path: Path, report: Mapping[str, object]) -> None:
    write_json_atomic(path, dict(report))
