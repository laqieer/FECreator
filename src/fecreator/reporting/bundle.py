from __future__ import annotations

import os
import re
import shutil
import stat
import uuid
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from fecreator.contracts.diagnostics import Diagnostic, Severity, error
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.core.atomicio import (
    LockTimeoutError,
    _fsync_directory,
    _path_lock,
    _read_json_unlocked,
    _write_json_atomic_unlocked,
)
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.core.redaction import contains_secret_key
from fecreator.interop.febuilder_roundtrip import (
    RoundtripEvidence,
    decode_package_digest,
    decode_roundtrip,
)
from fecreator.jobs.approvals import ApprovalRecord
from fecreator.jobs.model import Job
from fecreator.reporting.sanitize import (
    JsonObject,
    JsonValue,
    as_object,
    sanitize_json,
    sanitize_path,
    sanitize_text,
)

MAX_BUNDLE_FILE_COUNT = 64
MAX_BUNDLE_BYTES = 32 * 1024 * 1024
STAGING_PREFIX = ".bundle-stage-"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_COMPAT_SOURCE = "deterministic_febuilder_compatible_roundtrip"
_REQUIRED_BUNDLE_FILES = frozenset(
    {"compat.json", "manifest.json", "report.json", "lineage.json", "hashes.json"}
)
_REQUIRED_REPORT_KEYS = frozenset(
    {
        "job_id",
        "manifest",
        "manifest_hash",
        "approval",
        "stages",
        "diagnostics",
        "lineage",
        "output_hashes",
    }
)


class BundleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    size_bytes: int = Field(ge=0)


class BundleError(Exception):
    """Raised when a bundle cannot be created safely."""


def _bundle_lock_path(out_dir: Path) -> Path:
    return out_dir.parent / f".{out_dir.name}.lock"


def _read_json_object(path: Path, *, label: str) -> JsonObject:
    try:
        payload = _read_json_unlocked(path)
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {path.name}") from exc
    except Exception as exc:
        raise BundleError(f"cannot parse {label}: {path.name}") from exc
    if not isinstance(payload, dict):
        raise BundleError(f"{label} must contain a JSON object: {path.name}")
    return cast(JsonObject, payload)


def _read_json_list(path: Path, *, label: str) -> list[JsonObject]:
    try:
        payload = _read_json_unlocked(path)
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {path.name}") from exc
    except Exception as exc:
        raise BundleError(f"cannot parse {label}: {path.name}") from exc
    if not isinstance(payload, list):
        raise BundleError(f"{label} must contain a JSON array: {path.name}")
    objects: list[JsonObject] = []
    for item in payload:
        if not isinstance(item, dict):
            raise BundleError(f"{label} must contain only JSON objects: {path.name}")
        objects.append(cast(JsonObject, item))
    return objects


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _REPARSE_POINT)


def _is_unsafe_entry(path: Path) -> bool:
    return path.is_symlink() or _is_reparse_point(path)


def _is_regular_file(path: Path) -> bool:
    try:
        path.lstat()
        return bool(path.is_file())
    except OSError:
        return False


def _iter_tree(root: Path) -> list[Path]:
    stack = [root]
    files: list[Path] = []
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir(), key=lambda item: item.name, reverse=True):
            if _is_unsafe_entry(entry):
                raise BundleError(f"unsafe path detected: {entry.name}")
            if entry.is_dir():
                stack.append(entry)
                continue
            if not _is_regular_file(entry):
                raise BundleError(f"unsupported filesystem entry: {entry.name}")
            if entry.stat(follow_symlinks=False).st_nlink > 1:
                raise BundleError(f"hard-linked files are not supported in bundles: {entry.name}")
            files.append(entry)
    return sorted(files)


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _casefold_collisions(paths: Iterable[str]) -> dict[str, list[str]]:
    by_casefold: dict[str, list[str]] = {}
    for path in sorted(paths):
        by_casefold.setdefault(path.replace("\\", "/").casefold(), []).append(path)
    return {
        folded: values
        for folded, values in by_casefold.items()
        if len({value for value in values}) > 1
    }


def _validate_package_tree(package_dir: Path) -> list[Path]:
    if not package_dir.exists() or not package_dir.is_dir():
        raise BundleError("missing canonical package directory")
    package_files = _iter_tree(package_dir)
    if not package_files:
        raise BundleError("package directory is empty")
    unsupported = [path for path in package_files if path.suffix.lower() not in {".png", ".pal"}]
    if unsupported:
        names = ", ".join(_relative_posix(package_dir, path) for path in unsupported)
        raise BundleError(f"unsupported package files: {names}")
    return package_files


def _check_resource_limits(files: Iterable[Path]) -> None:
    file_list = list(files)
    if len(file_list) > MAX_BUNDLE_FILE_COUNT:
        raise BundleError(
            f"bundle file count limit exceeded: {len(file_list)} > {MAX_BUNDLE_FILE_COUNT}"
        )
    total_bytes = sum(path.stat().st_size for path in file_list)
    if total_bytes > MAX_BUNDLE_BYTES:
        raise BundleError(f"bundle byte limit exceeded: {total_bytes} > {MAX_BUNDLE_BYTES}")


def _copy_regular_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _stage_dir_for(out_dir: Path) -> Path:
    return out_dir.parent / f"{STAGING_PREFIX}{out_dir.name}-{uuid.uuid4().hex}"


def _hash_files(root: Path) -> dict[str, str]:
    return {
        _relative_posix(root, path): sha256_file(path)
        for path in _iter_tree(root)
        if _relative_posix(root, path) != "hashes.json"
    }


def _validated_lineage_payload(payload: list[JsonObject]) -> list[JsonObject]:
    nodes = [LineageNode.model_validate(item) for item in payload]
    sanitized = [
        as_object(sanitize_json(node.model_dump(mode="json"), error_cls=BundleError))
        for node in nodes
    ]
    for node in sanitized:
        node["output_hashes"] = cast(JsonValue, sorted(cast(list[str], node["output_hashes"])))
    return sorted(
        sanitized,
        key=lambda item: (cast(str, item["created_at"]), cast(str, item["asset_id"])),
    )


def _as_object_list(value: JsonValue, *, label: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise BundleError(f"{label} must contain a JSON array")
    objects: list[JsonObject] = []
    for item in value:
        if not isinstance(item, dict):
            raise BundleError(f"{label} must contain only JSON objects")
        objects.append(item)
    return objects


def _as_string_list(value: JsonValue, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise BundleError(f"{label} must contain a JSON array")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise BundleError(f"{label} must contain only strings")
        strings.append(item)
    return strings


def _sort_diagnostics(diagnostics: Iterable[JsonObject]) -> list[JsonObject]:
    return sorted(
        diagnostics,
        key=lambda diagnostic: (
            cast(str, diagnostic["severity"]),
            cast(str, diagnostic["code"]),
            cast(str | None, diagnostic["where"]) or "",
            cast(str, diagnostic["message"]),
        ),
    )


def _sort_stage(stage: JsonObject) -> JsonObject:
    artifacts = sorted(
        _as_object_list(stage.get("artifacts", []), label="report.stages.artifacts"),
        key=lambda artifact: (
            cast(str, artifact["role"]),
            cast(str, artifact["path"]),
            cast(str, artifact["sha256"]),
        ),
    )
    diagnostics = _sort_diagnostics(
        _as_object_list(
            stage.get("diagnostics", []),
            label="report.stages.diagnostics",
        )
    )
    return {
        **stage,
        "artifacts": cast(JsonValue, artifacts),
        "diagnostics": cast(JsonValue, diagnostics),
    }


def _validated_report_payload(payload: JsonObject) -> JsonObject:
    sanitized = as_object(sanitize_json(payload, error_cls=BundleError))
    missing = sorted(_REQUIRED_REPORT_KEYS - set(sanitized))
    if missing:
        raise BundleError(f"report.json is missing required keys: {', '.join(missing)}")
    stages = sorted(
        (
            _sort_stage(stage)
            for stage in _as_object_list(sanitized["stages"], label="report.stages")
        ),
        key=lambda item: cast(str, item["stage"]),
    )
    diagnostics = _sort_diagnostics(
        _as_object_list(sanitized["diagnostics"], label="report.diagnostics")
    )
    approval = sanitized["approval"]
    if approval is not None:
        if not isinstance(approval, dict):
            raise BundleError("report.approval must contain an object or null")
        approval = as_object(
            sanitize_json(
                ApprovalRecord.model_validate(approval).model_dump(mode="json"),
                error_cls=BundleError,
            )
        )
    _as_object_list(sanitized["lineage"], label="report.lineage")
    _as_string_list(sanitized["output_hashes"], label="report.output_hashes")
    return {
        **sanitized,
        "approval": approval,
        "stages": cast(JsonValue, stages),
        "diagnostics": cast(JsonValue, diagnostics),
    }


def _normalize_declared_relative_path(relative_path: str) -> str:
    if "\\" in relative_path:
        raise BundleError(f"unsafe bundle path uses backslashes: {relative_path}")
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or relative_path.startswith("//"):
        raise BundleError(f"unsafe bundle path: {relative_path}")
    if not posix.parts:
        raise BundleError(f"unsafe bundle path: {relative_path}")
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise BundleError(f"unsafe bundle path: {relative_path}")
    if any(len(part) >= 2 and part[1] == ":" for part in posix.parts):
        raise BundleError(f"unsafe bundle path: {relative_path}")
    return posix.as_posix()


def _validated_declared_path(bundle_dir: Path, relative_path: str) -> tuple[str, Path]:
    normalized = _normalize_declared_relative_path(relative_path)
    try:
        target = safe_join(bundle_dir, *PurePosixPath(normalized).parts)
    except PathEscapeError as exc:
        raise BundleError(f"unsafe bundle path: {relative_path}") from exc
    return normalized, target


def _scan_bundle_files(bundle_dir: Path) -> list[str]:
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return []
    relative_files = [_relative_posix(bundle_dir, path) for path in _iter_tree(bundle_dir)]
    collisions = _casefold_collisions(relative_files)
    if collisions:
        collided = next(iter(collisions.values()))
        raise BundleError(f"casefold collision in bundle paths: {', '.join(collided)}")
    return relative_files


def _package_hashes_from_stage(stage_dir: Path) -> dict[str, str]:
    package_root = stage_dir / "package"
    return {
        _relative_posix(stage_dir, path): sha256_file(path) for path in _iter_tree(package_root)
    }


def _report_output_hashes(
    package_hashes: Iterable[str],
    lineage_payload: Iterable[JsonObject],
) -> list[str]:
    return sorted(
        set(package_hashes)
        | {
            hash_value
            for node in lineage_payload
            for hash_value in cast(list[str], node["output_hashes"])
        }
    )


def _canonicalize_report_payload(
    job: Job,
    report_payload: JsonObject,
    manifest_payload: JsonObject,
    lineage_payload: list[JsonObject],
    package_hashes: dict[str, str],
) -> JsonObject:
    sanitized = _validated_report_payload(report_payload)
    return {
        **sanitized,
        "job_id": job.id,
        "state": job.state.value,
        "revision": job.revision,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "manifest": cast(JsonValue, manifest_payload),
        "manifest_hash": job.manifest.content_hash(),
        "lineage": cast(JsonValue, lineage_payload),
        "output_hashes": cast(
            JsonValue,
            _report_output_hashes(package_hashes.values(), lineage_payload),
        ),
    }


def build_bundle(job: Job, workspace: Path, out_dir: Path) -> Path:
    for key in job.manifest.params:
        if contains_secret_key(key):
            raise BundleError(f"manifest param names a credential: {key}")
    workspace_root = workspace.resolve(strict=True)
    package_dir = safe_join(workspace_root, "package")
    report_path = safe_join(workspace_root, "report.json")
    lineage_path = safe_join(workspace_root, "lineage.json")

    package_files = _validate_package_tree(package_dir)
    manifest_payload = as_object(
        sanitize_json(job.manifest.model_dump(mode="json"), error_cls=BundleError)
    )
    raw_report_payload = _read_json_object(report_path, label="report")
    raw_lineage_payload = _read_json_list(lineage_path, label="lineage")
    lineage_payload = _validated_lineage_payload(raw_lineage_payload)
    compat_payload = febuilder_compat_report(decode_roundtrip(package_dir))
    _check_resource_limits([*package_files, report_path, lineage_path])

    try:
        with _path_lock(out_dir, lock_path=_bundle_lock_path(out_dir)):
            if out_dir.exists():
                raise BundleError(
                    f"bundle destination already exists; refusing to overwrite: {out_dir}"
                )

            staging_dir = _stage_dir_for(out_dir)
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

            try:
                staging_dir.mkdir(parents=True, exist_ok=False)
                _write_json_atomic_unlocked(staging_dir / "manifest.json", manifest_payload)
                _write_json_atomic_unlocked(staging_dir / "lineage.json", lineage_payload)
                _write_json_atomic_unlocked(staging_dir / "compat.json", compat_payload)
                for source in package_files:
                    relative = source.relative_to(package_dir)
                    _copy_regular_file(source, staging_dir / "package" / relative)
                package_hashes = _package_hashes_from_stage(staging_dir)
                report_payload = _canonicalize_report_payload(
                    job,
                    raw_report_payload,
                    manifest_payload,
                    lineage_payload,
                    package_hashes,
                )
                _write_json_atomic_unlocked(staging_dir / "report.json", report_payload)
                hashes_payload = {"algorithm": "sha256", "files": _hash_files(staging_dir)}
                _write_json_atomic_unlocked(staging_dir / "hashes.json", hashes_payload)
                os.replace(staging_dir, out_dir)
                _fsync_directory(out_dir.parent)
            except Exception:
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise
    except LockTimeoutError as exc:
        destination = sanitize_path(out_dir.name or "bundle")
        raise BundleError(
            f"bundle destination lock contention while publishing to {destination}"
        ) from exc
    return out_dir


def _report_missing_file(name: str, diagnostics: list[Diagnostic], missing: set[str]) -> None:
    """Record one missing bundle file so later scans do not repeat the finding."""
    if name in missing:
        return
    missing.add(name)
    diagnostics.append(error("BUNDLE_MISSING_FILE", f"missing {name}", where=name))


def _validate_manifest_file(
    bundle_dir: Path, diagnostics: list[Diagnostic], missing: set[str]
) -> Manifest | None:
    path = bundle_dir / "manifest.json"
    if not path.is_file():
        _report_missing_file("manifest.json", diagnostics, missing)
        return None
    try:
        return Manifest.model_validate(_read_json_unlocked(path))
    except (OSError, ValueError) as exc:
        diagnostics.append(
            error(
                "BUNDLE_INVALID_MANIFEST",
                f"manifest.json is invalid: {sanitize_text(str(exc))}",
                where="manifest.json",
            )
        )
    return None


def _validate_report_file(
    bundle_dir: Path, diagnostics: list[Diagnostic], missing: set[str]
) -> JsonObject | None:
    path = bundle_dir / "report.json"
    if not path.is_file():
        _report_missing_file("report.json", diagnostics, missing)
        return None
    try:
        payload = _read_json_object(path, label="report")
        return _validated_report_payload(payload)
    except BundleError as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_REPORT", sanitize_text(str(exc)), where="report.json")
        )
    return None


def _validate_lineage_file(
    bundle_dir: Path, diagnostics: list[Diagnostic], missing: set[str]
) -> list[JsonObject] | None:
    path = bundle_dir / "lineage.json"
    if not path.is_file():
        _report_missing_file("lineage.json", diagnostics, missing)
        return None
    try:
        payload = _read_json_list(path, label="lineage")
        return _validated_lineage_payload(payload)
    except BundleError as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_LINEAGE", sanitize_text(str(exc)), where="lineage.json")
        )
    except (OSError, ValueError) as exc:
        diagnostics.append(
            error(
                "BUNDLE_INVALID_LINEAGE",
                sanitize_text(f"lineage.json is invalid: {exc}"),
                where="lineage.json",
            )
        )
    return None


def _validate_hashes_file(
    bundle_dir: Path, diagnostics: list[Diagnostic], missing: set[str]
) -> JsonObject | None:
    path = bundle_dir / "hashes.json"
    if not path.is_file():
        _report_missing_file("hashes.json", diagnostics, missing)
        return None
    try:
        payload = _read_json_object(path, label="hashes")
    except BundleError as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_HASHES", sanitize_text(str(exc)), where="hashes.json")
        )
        return None
    if payload.get("algorithm") != "sha256":
        diagnostics.append(
            error(
                "BUNDLE_INVALID_HASHES",
                "hashes.json must declare algorithm=sha256",
                where="hashes.json",
            )
        )
    if not isinstance(payload.get("files"), dict):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_HASHES",
                "hashes.json must contain a files mapping",
                where="hashes.json",
            )
        )
        return None
    return payload


def _validate_compat_file(
    bundle_dir: Path, diagnostics: list[Diagnostic], missing: set[str]
) -> RoundtripEvidence | None:
    path = bundle_dir / "compat.json"
    if not path.is_file():
        _report_missing_file("compat.json", diagnostics, missing)
        return None
    try:
        payload = _read_json_object(path, label="compatibility evidence")
    except BundleError as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_COMPAT", sanitize_text(str(exc)), where="compat.json")
        )
        return None

    if payload.get("source") != _COMPAT_SOURCE:
        diagnostics.append(
            error(
                "BUNDLE_INVALID_COMPAT",
                "compat.json has an unexpected compatibility source",
                where="compat.json",
            )
        )
        return None
    if payload.get("validated_by_cli") is not False:
        diagnostics.append(
            error(
                "BUNDLE_INVALID_COMPAT",
                "compat.json must not claim external CLI validation",
                where="compat.json",
            )
        )
        return None
    try:
        evidence = RoundtripEvidence.model_validate(payload["roundtrip"])
    except (KeyError, TypeError, ValueError):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_COMPAT",
                "compat.json roundtrip evidence is malformed",
                where="compat.json",
            )
        )
        return None
    if any(not _is_sanitized_diagnostic(diagnostic) for diagnostic in evidence.diagnostics):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_COMPAT",
                "compat.json roundtrip diagnostics contain unsafe text or paths",
                where="compat.json",
            )
        )
        return None
    return evidence


def _is_sanitized_diagnostic(diagnostic: Diagnostic) -> bool:
    if diagnostic.message != sanitize_text(diagnostic.message):
        return False
    if diagnostic.where is not None and diagnostic.where != sanitize_path(diagnostic.where):
        return False
    return all(
        value == sanitize_text(value)
        for value in (diagnostic.data or {}).values()
        if isinstance(value, str)
    )


def _verify_compat_matches_package(
    bundle_dir: Path, compat: RoundtripEvidence, diagnostics: list[Diagnostic]
) -> None:
    """Bind successful roundtrip evidence to the package bytes in this bundle.

    Structurally valid evidence copied from another package must not verify, so
    the bundled package is decoded again and compared against the recorded
    geometry, palette size, earned background index, and array hashes.
    """
    digest = decode_package_digest(bundle_dir / "package")
    if digest is None:
        diagnostics.append(
            error(
                "BUNDLE_COMPAT_EVIDENCE_MISMATCH",
                "compat.json reports success but the bundled package cannot be decoded",
                where="compat.json",
            )
        )
        return
    recorded = (
        compat.dimensions,
        compat.color_count,
        compat.background_index,
        compat.pixel_sha256,
        compat.palette_sha256,
    )
    decoded = (
        digest.dimensions,
        digest.color_count,
        digest.background_index,
        digest.pixel_sha256,
        digest.palette_sha256,
    )
    if recorded != decoded:
        diagnostics.append(
            error(
                "BUNDLE_COMPAT_EVIDENCE_MISMATCH",
                "compat.json roundtrip evidence does not describe the bundled package",
                where="compat.json",
            )
        )


def _append_casefold_collision_diagnostics(
    collisions: dict[str, list[str]], diagnostics: list[Diagnostic]
) -> set[str]:
    duplicates: set[str] = set()
    for paths in collisions.values():
        sorted_paths = sorted(paths)
        duplicates.update(sorted_paths)
        diagnostics.append(
            error(
                "BUNDLE_UNSAFE_PATH",
                f"casefold collision in bundle paths: {', '.join(sorted_paths)}",
                where=sorted_paths[-1],
            )
        )
    return duplicates


def verify_bundle(bundle_dir: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return [
            error(
                "BUNDLE_MISSING_ROOT",
                "bundle directory does not exist",
                where=sanitize_path(bundle_dir.name or "bundle"),
            )
        ]

    missing_files: set[str] = set()
    manifest = _validate_manifest_file(bundle_dir, diagnostics, missing_files)
    report = _validate_report_file(bundle_dir, diagnostics, missing_files)
    lineage = _validate_lineage_file(bundle_dir, diagnostics, missing_files)
    compat = _validate_compat_file(bundle_dir, diagnostics, missing_files)
    hashes_payload = _validate_hashes_file(bundle_dir, diagnostics, missing_files)
    if hashes_payload is None:
        return diagnostics

    declared = hashes_payload.get("files")
    if not isinstance(declared, dict):
        return diagnostics

    try:
        actual_file_list = _scan_bundle_files(bundle_dir)
    except BundleError as exc:
        diagnostics.append(error("BUNDLE_UNSAFE_PATH", sanitize_text(str(exc)), where="bundle"))
        return diagnostics
    actual_files = set(actual_file_list)
    skipped_declared = _append_casefold_collision_diagnostics(
        _casefold_collisions(cast(list[str], [key for key in declared if isinstance(key, str)])),
        diagnostics,
    )
    _append_casefold_collision_diagnostics(_casefold_collisions(actual_file_list), diagnostics)

    expected_files = {"hashes.json"}
    package_hashes: dict[str, str] = {}
    for relative_path, expected_hash in sorted(declared.items(), key=lambda item: str(item[0])):
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            diagnostics.append(
                error(
                    "BUNDLE_INVALID_HASHES",
                    "hash entries must be string->string",
                    where="hashes.json",
                )
            )
            continue
        if relative_path in skipped_declared:
            continue
        if not _HASH_RE.fullmatch(expected_hash):
            diagnostics.append(
                error(
                    "BUNDLE_INVALID_HASHES",
                    f"declared hash is not a lowercase sha256 digest: {relative_path}",
                    where="hashes.json",
                )
            )
            continue
        try:
            normalized_path, target = _validated_declared_path(bundle_dir, relative_path)
        except BundleError as exc:
            diagnostics.append(
                error("BUNDLE_UNSAFE_PATH", sanitize_text(str(exc)), where=relative_path)
            )
            continue
        except PathEscapeError as exc:
            diagnostics.append(
                error("BUNDLE_UNSAFE_PATH", sanitize_text(str(exc)), where=relative_path)
            )
            continue

        expected_files.add(normalized_path)
        if not target.exists():
            if normalized_path not in missing_files:
                missing_files.add(normalized_path)
                diagnostics.append(
                    error(
                        "BUNDLE_MISSING_FILE",
                        f"declared file is missing: {normalized_path}",
                        where=normalized_path,
                    )
                )
            continue
        if _is_unsafe_entry(target):
            diagnostics.append(
                error(
                    "BUNDLE_UNSAFE_PATH",
                    f"declared file is unsafe: {normalized_path}",
                    where=normalized_path,
                )
            )
            continue
        if target.stat(follow_symlinks=False).st_nlink > 1:
            diagnostics.append(
                error(
                    "BUNDLE_UNSAFE_PATH",
                    f"declared file is hard-linked: {normalized_path}",
                    where=normalized_path,
                )
            )
            continue
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            diagnostics.append(
                error(
                    "BUNDLE_HASH_MISMATCH",
                    f"declared sha256 {expected_hash} does not match actual {actual_hash}",
                    where=normalized_path,
                )
            )
        if normalized_path.startswith("package/"):
            package_hashes[normalized_path] = expected_hash

    for relative_path in sorted(actual_files - expected_files):
        diagnostics.append(
            error(
                "BUNDLE_EXTRA_FILE",
                f"unexpected file present: {relative_path}",
                where=relative_path,
            )
        )

    for relative_path in sorted(_REQUIRED_BUNDLE_FILES - actual_files - missing_files):
        diagnostics.append(
            error(
                "BUNDLE_MISSING_FILE",
                f"missing required bundle file: {relative_path}",
                where=relative_path,
            )
        )

    if compat is not None:
        if compat.ok:
            _verify_compat_matches_package(bundle_dir, compat, diagnostics)
        else:
            diagnostics.append(
                error(
                    "BUNDLE_COMPAT_FAILURE",
                    "deterministic compatibility roundtrip did not succeed",
                    where="compat.json",
                )
            )

    if manifest is not None and report is not None and lineage is not None:
        expected_manifest_hash = manifest.content_hash()
        if report.get("manifest_hash") != expected_manifest_hash:
            diagnostics.append(
                error(
                    "BUNDLE_INCONSISTENT_MANIFEST_HASH",
                    "report.manifest_hash does not match manifest.json",
                    where="report.json",
                )
            )

        report_lineage = _as_object_list(report["lineage"], label="report.lineage")
        if report_lineage != lineage:
            diagnostics.append(
                error(
                    "BUNDLE_INCONSISTENT_LINEAGE",
                    "report.lineage does not match lineage.json",
                    where="report.json",
                )
            )

        report_output_hashes = sorted(
            _as_string_list(report["output_hashes"], label="report.output_hashes")
        )
        expected_output_hashes = _report_output_hashes(package_hashes.values(), lineage)
        if report_output_hashes != expected_output_hashes:
            diagnostics.append(
                error(
                    "BUNDLE_INCONSISTENT_OUTPUT_HASHES",
                    "report.output_hashes does not match package and lineage hashes",
                    where="report.json",
                )
            )

    return diagnostics


def febuilder_compat_report(evidence: RoundtripEvidence) -> dict[str, object]:
    diagnostics = sorted(
        evidence.diagnostics,
        key=lambda diagnostic: (
            diagnostic.severity.value,
            diagnostic.code,
            diagnostic.where or "",
            diagnostic.message,
        ),
    )
    return {
        "source": _COMPAT_SOURCE,
        "validated_by_cli": False,
        "roundtrip": evidence.model_dump(mode="json"),
        "errors": sum(1 for diagnostic in diagnostics if diagnostic.severity is Severity.ERROR),
        "warnings": sum(1 for diagnostic in diagnostics if diagnostic.severity is Severity.WARNING),
        "infos": sum(1 for diagnostic in diagnostics if diagnostic.severity is Severity.INFO),
        "codes": sorted({diagnostic.code for diagnostic in diagnostics}),
        "diagnostics": [
            {
                "code": diagnostic.code,
                "severity": diagnostic.severity.value,
                "message": sanitize_text(diagnostic.message),
                "where": sanitize_path(diagnostic.where) if diagnostic.where else None,
            }
            for diagnostic in diagnostics
        ],
    }
