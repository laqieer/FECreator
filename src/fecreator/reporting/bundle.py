from __future__ import annotations

import os
import re
import shutil
import stat
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypeAlias, cast

from fecreator.contracts.diagnostics import Diagnostic, Severity, error
from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.manifest import Manifest
from fecreator.core.atomicio import (
    _fsync_directory,
    _read_json_unlocked,
    _write_json_atomic_unlocked,
)
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import safe_join
from fecreator.core.redaction import contains_secret_key, redact
from fecreator.jobs.model import Job

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

MAX_BUNDLE_FILE_COUNT = 64
MAX_BUNDLE_BYTES = 32 * 1024 * 1024
STAGING_PREFIX = ".bundle-stage-"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_REQUIRED_BUNDLE_FILES = frozenset({"manifest.json", "report.json", "lineage.json", "hashes.json"})


class BundleError(Exception):
    """Raised when a bundle cannot be created safely."""


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
                raise BundleError(f"credential-like key is not allowed in bundle payload: {key}")
            sanitized[key] = _sanitize_json(value[key])
        return sanitized
    if isinstance(value, tuple | list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    raise BundleError(f"unsupported bundle payload value: {type(value)!r}")


def _load_json_object(path: Path, *, label: str) -> JsonObject:
    try:
        payload = _read_json_unlocked(path)
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {path.name}") from exc
    except Exception as exc:
        raise BundleError(f"cannot parse {label}: {path.name}") from exc
    if not isinstance(payload, dict):
        raise BundleError(f"{label} must contain a JSON object: {path.name}")
    return cast(JsonObject, _sanitize_json(payload))


def _load_json_list(path: Path, *, label: str) -> list[JsonObject]:
    try:
        payload = _read_json_unlocked(path)
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {path.name}") from exc
    except Exception as exc:
        raise BundleError(f"cannot parse {label}: {path.name}") from exc
    if not isinstance(payload, list):
        raise BundleError(f"{label} must contain a JSON array: {path.name}")
    return [cast(JsonObject, _sanitize_json(item)) for item in payload]


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
    sanitized = [cast(JsonObject, _sanitize_json(node.model_dump(mode="json"))) for node in nodes]
    for node in sanitized:
        node["output_hashes"] = cast(JsonValue, sorted(cast(list[str], node["output_hashes"])))
    return sorted(
        sanitized,
        key=lambda item: (cast(str, item["created_at"]), cast(str, item["asset_id"])),
    )


def _validated_report_payload(payload: JsonObject) -> JsonObject:
    required = {
        "job_id",
        "manifest",
        "manifest_hash",
        "stages",
        "diagnostics",
        "lineage",
        "output_hashes",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise BundleError(f"report.json is missing required keys: {', '.join(missing)}")
    return payload


def build_bundle(job: Job, workspace: Path, out_dir: Path) -> Path:
    for key in job.manifest.params:
        if contains_secret_key(key):
            raise BundleError(f"manifest param names a credential: {key}")
    if out_dir.exists():
        raise BundleError(f"bundle destination already exists; refusing to overwrite: {out_dir}")

    workspace_root = workspace.resolve(strict=True)
    package_dir = safe_join(workspace_root, "package")
    report_path = safe_join(workspace_root, "report.json")
    lineage_path = safe_join(workspace_root, "lineage.json")

    package_files = _validate_package_tree(package_dir)
    manifest_payload = cast(JsonObject, _sanitize_json(job.manifest.model_dump(mode="json")))
    report_payload = _validated_report_payload(_load_json_object(report_path, label="report"))
    lineage_payload = _validated_lineage_payload(_load_json_list(lineage_path, label="lineage"))
    _check_resource_limits([*package_files, report_path, lineage_path])

    staging_dir = _stage_dir_for(out_dir)
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    try:
        staging_dir.mkdir(parents=True, exist_ok=False)
        _write_json_atomic_unlocked(staging_dir / "manifest.json", manifest_payload)
        _write_json_atomic_unlocked(staging_dir / "report.json", report_payload)
        _write_json_atomic_unlocked(staging_dir / "lineage.json", lineage_payload)
        for source in package_files:
            relative = source.relative_to(package_dir)
            _copy_regular_file(source, staging_dir / "package" / relative)
        hashes_payload = {"algorithm": "sha256", "files": _hash_files(staging_dir)}
        _write_json_atomic_unlocked(staging_dir / "hashes.json", hashes_payload)
        os.replace(staging_dir, out_dir)
        _fsync_directory(out_dir.parent)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return out_dir


def _validate_declared_path(bundle_dir: Path, relative_path: str) -> Path:
    if "\\" in relative_path:
        raise BundleError(f"unsafe bundle path uses backslashes: {relative_path}")
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or ".." in posix.parts or "." in posix.parts:
        raise BundleError(f"unsafe bundle path: {relative_path}")
    return safe_join(bundle_dir, *posix.parts)


def _scan_bundle_files(bundle_dir: Path) -> list[str]:
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return []
    return [_relative_posix(bundle_dir, path) for path in _iter_tree(bundle_dir)]


def _validate_manifest_file(bundle_dir: Path, diagnostics: list[Diagnostic]) -> None:
    path = bundle_dir / "manifest.json"
    try:
        Manifest.model_validate(_read_json_unlocked(path))
    except FileNotFoundError:
        diagnostics.append(
            error("BUNDLE_MISSING_FILE", "missing manifest.json", where="manifest.json")
        )
    except Exception as exc:
        diagnostics.append(
            error(
                "BUNDLE_INVALID_MANIFEST", f"manifest.json is invalid: {exc}", where="manifest.json"
            )
        )


def _validate_report_file(bundle_dir: Path, diagnostics: list[Diagnostic]) -> None:
    path = bundle_dir / "report.json"
    try:
        payload = _read_json_unlocked(path)
    except FileNotFoundError:
        diagnostics.append(error("BUNDLE_MISSING_FILE", "missing report.json", where="report.json"))
        return
    except Exception as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_REPORT", f"report.json is invalid: {exc}", where="report.json")
        )
        return
    if not isinstance(payload, dict):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_REPORT", "report.json must contain an object", where="report.json"
            )
        )
        return
    missing = sorted(
        {"job_id", "manifest", "manifest_hash", "stages", "diagnostics", "lineage", "output_hashes"}
        - set(payload)
    )
    if missing:
        diagnostics.append(
            error(
                "BUNDLE_INVALID_REPORT",
                f"report.json is missing required keys: {', '.join(missing)}",
                where="report.json",
            )
        )


def _validate_lineage_file(bundle_dir: Path, diagnostics: list[Diagnostic]) -> None:
    path = bundle_dir / "lineage.json"
    try:
        payload = _read_json_unlocked(path)
    except FileNotFoundError:
        diagnostics.append(
            error("BUNDLE_MISSING_FILE", "missing lineage.json", where="lineage.json")
        )
        return
    except Exception as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_LINEAGE", f"lineage.json is invalid: {exc}", where="lineage.json")
        )
        return
    if not isinstance(payload, list):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_LINEAGE", "lineage.json must contain an array", where="lineage.json"
            )
        )
        return
    for index, item in enumerate(payload):
        try:
            LineageNode.model_validate(item)
        except Exception as exc:
            diagnostics.append(
                error(
                    "BUNDLE_INVALID_LINEAGE",
                    f"lineage entry {index} is invalid: {exc}",
                    where="lineage.json",
                )
            )


def verify_bundle(bundle_dir: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return [
            error("BUNDLE_MISSING_ROOT", "bundle directory does not exist", where=str(bundle_dir))
        ]

    _validate_manifest_file(bundle_dir, diagnostics)
    _validate_report_file(bundle_dir, diagnostics)
    _validate_lineage_file(bundle_dir, diagnostics)

    hashes_path = bundle_dir / "hashes.json"
    try:
        hashes_payload = _read_json_unlocked(hashes_path)
    except FileNotFoundError:
        diagnostics.append(error("BUNDLE_MISSING_FILE", "missing hashes.json", where="hashes.json"))
        return diagnostics
    except Exception as exc:
        diagnostics.append(
            error("BUNDLE_INVALID_HASHES", f"hashes.json is invalid: {exc}", where="hashes.json")
        )
        return diagnostics

    if not isinstance(hashes_payload, dict):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_HASHES", "hashes.json must contain an object", where="hashes.json"
            )
        )
        return diagnostics
    if hashes_payload.get("algorithm") != "sha256":
        diagnostics.append(
            error(
                "BUNDLE_INVALID_HASHES",
                "hashes.json must declare algorithm=sha256",
                where="hashes.json",
            )
        )
    declared = hashes_payload.get("files")
    if not isinstance(declared, dict):
        diagnostics.append(
            error(
                "BUNDLE_INVALID_HASHES",
                "hashes.json must contain a files mapping",
                where="hashes.json",
            )
        )
        return diagnostics

    actual_files: set[str]
    try:
        actual_files = set(_scan_bundle_files(bundle_dir))
    except BundleError as exc:
        diagnostics.append(error("BUNDLE_UNSAFE_PATH", str(exc), where="bundle"))
        return diagnostics
    expected_files = set(declared) | {"hashes.json"}

    for relative_path, expected_hash in declared.items():
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            diagnostics.append(
                error(
                    "BUNDLE_INVALID_HASHES",
                    "hash entries must be string->string",
                    where="hashes.json",
                )
            )
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
            target = _validate_declared_path(bundle_dir, relative_path)
        except BundleError as exc:
            diagnostics.append(error("BUNDLE_UNSAFE_PATH", str(exc), where=relative_path))
            continue
        if not target.exists():
            diagnostics.append(
                error(
                    "BUNDLE_MISSING_FILE",
                    f"declared file is missing: {relative_path}",
                    where=relative_path,
                )
            )
            continue
        if _is_unsafe_entry(target):
            diagnostics.append(
                error(
                    "BUNDLE_UNSAFE_PATH",
                    f"declared file is unsafe: {relative_path}",
                    where=relative_path,
                )
            )
            continue
        if target.stat(follow_symlinks=False).st_nlink > 1:
            diagnostics.append(
                error(
                    "BUNDLE_UNSAFE_PATH",
                    f"declared file is hard-linked: {relative_path}",
                    where=relative_path,
                )
            )
            continue
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            diagnostics.append(
                error(
                    "BUNDLE_HASH_MISMATCH",
                    f"declared sha256 {expected_hash} does not match actual {actual_hash}",
                    where=relative_path,
                )
            )

    extra_files = sorted(actual_files - expected_files)
    for relative_path in extra_files:
        diagnostics.append(
            error(
                "BUNDLE_EXTRA_FILE",
                f"unexpected file present: {relative_path}",
                where=relative_path,
            )
        )

    missing_required = sorted(_REQUIRED_BUNDLE_FILES - actual_files)
    for relative_path in missing_required:
        diagnostics.append(
            error(
                "BUNDLE_MISSING_FILE",
                f"missing required bundle file: {relative_path}",
                where=relative_path,
            )
        )

    return diagnostics


def febuilder_compat_report(diags: Iterable[Diagnostic]) -> dict[str, object]:
    diagnostics = sorted(
        diags,
        key=lambda diagnostic: (
            diagnostic.severity.value,
            diagnostic.code,
            diagnostic.where or "",
            diagnostic.message,
        ),
    )
    return {
        "source": "canonical_gba_validation",
        "validated_by_cli": False,
        "errors": sum(1 for diagnostic in diagnostics if diagnostic.severity is Severity.ERROR),
        "warnings": sum(1 for diagnostic in diagnostics if diagnostic.severity is Severity.WARNING),
        "infos": sum(1 for diagnostic in diagnostics if diagnostic.severity is Severity.INFO),
        "codes": sorted({diagnostic.code for diagnostic in diagnostics}),
        "diagnostics": [
            {
                "code": diagnostic.code,
                "severity": diagnostic.severity.value,
                "message": _sanitize_string(diagnostic.message),
                "where": _sanitize_string(diagnostic.where) if diagnostic.where else None,
            }
            for diagnostic in diagnostics
        ],
    }
