from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypeAlias, cast

from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.result import StageResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.core.redaction import contains_secret_key, redact
from fecreator.jobs.model import Job

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _looks_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _safe_path_display(value: str) -> str:
    windows_name = PureWindowsPath(value).name
    posix_name = PurePosixPath(value).name
    return windows_name or posix_name or value


def _sanitize_string(value: str) -> str:
    if _looks_absolute_path(value):
        value = _safe_path_display(value)
    return redact(value)


def _sanitize_json(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        sanitized: JsonObject = {}
        for key in sorted(value):
            if contains_secret_key(key):
                raise ValueError(f"credential-like key is not allowed in report payload: {key}")
            sanitized[key] = _sanitize_json(value[key])
        return sanitized
    if isinstance(value, tuple | list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    raise TypeError(f"unsupported report value: {type(value)!r}")


def _stage_payload(result: StageResult) -> JsonObject:
    payload = cast(JsonObject, _sanitize_json(result.model_dump(mode="json")))
    artifacts = sorted(
        cast(list[JsonObject], payload["artifacts"]),
        key=lambda artifact: (artifact["role"], artifact["path"], artifact["sha256"]),
    )
    diagnostics = sorted(
        cast(list[JsonObject], payload["diagnostics"]),
        key=lambda diagnostic: (
            diagnostic["severity"],
            diagnostic["code"],
            diagnostic["where"] or "",
            diagnostic["message"],
        ),
    )
    return cast(
        JsonObject,
        {
            **payload,
            "artifacts": cast(JsonValue, artifacts),
            "diagnostics": cast(JsonValue, diagnostics),
        },
    )


def _lineage_payload(node: LineageNode) -> JsonObject:
    payload = cast(JsonObject, _sanitize_json(node.model_dump(mode="json")))
    payload["output_hashes"] = cast(JsonValue, sorted(cast(list[str], payload["output_hashes"])))
    return payload


def build_report(
    job: Job, results: Sequence[StageResult], lineage: Sequence[LineageNode]
) -> JsonObject:
    manifest = cast(JsonObject, _sanitize_json(job.manifest.model_dump(mode="json")))
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
        key=lambda item: (item["severity"], item["code"], item["where"] or "", item["message"]),
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
    return cast(
        JsonObject,
        {
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
        },
    )


def write_report(path: Path, report: Mapping[str, object]) -> None:
    write_json_atomic(path, dict(report))
