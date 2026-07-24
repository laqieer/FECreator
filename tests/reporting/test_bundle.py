from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact, StageResult
from fecreator.core.atomicio import write_json_atomic
from fecreator.jobs.model import Job, JobState
from fecreator.reporting.bundle import (
    BundleError,
    build_bundle,
    febuilder_compat_report,
    verify_bundle,
)
from fecreator.reporting.json_report import build_report, write_report
from fecreator.specs.fire_emblem.gba.portrait_standard.validation import validate_package
from tests.fixtures.gba import write_valid_package


def _job(*, params: dict[str, str | int | float | bool] | None = None) -> Job:
    manifest = Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
        sources=(SourceSpec(kind="text", ref="hero"),),
        params=params or {},
    )
    return Job(
        id="job-1",
        state=JobState.COMPLETED,
        manifest=manifest,
        revision=2,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:01:00+00:00",
    )


def _lineage() -> list[LineageNode]:
    return [
        LineageNode(
            asset_id="asset-a",
            operation=Operation.EXPORT_SPEC,
            provider="fake",
            output_hashes=("a" * 64, "b" * 64),
            created_at="2026-07-24T00:02:00+00:00",
        )
    ]


def _workspace(tmp_path: Path, *, job: Job | None = None) -> tuple[Job, Path]:
    active_job = job or _job()
    workspace = tmp_path / "workspace"
    package_dir = workspace / "package"
    write_valid_package(package_dir)
    report = build_report(
        active_job,
        [
            StageResult(
                stage="export",
                ok=True,
                artifacts=(
                    Artifact(
                        role="sheet",
                        path="package\\hero.png",
                        sha256="c" * 64,
                        media_type="image/png",
                    ),
                ),
            )
        ],
        _lineage(),
    )
    write_report(workspace / "report.json", report)
    write_json_atomic(
        workspace / "lineage.json",
        [node.model_dump(mode="json") for node in _lineage()],
    )
    return active_job, workspace


def test_build_bundle_publishes_canonical_files_and_relative_hashes(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)

    bundle = build_bundle(job, workspace, tmp_path / "bundle")

    assert bundle == tmp_path / "bundle"
    assert (bundle / "manifest.json").exists()
    assert (bundle / "report.json").exists()
    assert (bundle / "lineage.json").exists()
    assert (bundle / "hashes.json").exists()
    assert (bundle / "package" / "hero.png").exists()
    assert (bundle / "package" / "hero.pal").exists()

    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    assert list(hashes["files"]) == sorted(hashes["files"])
    assert all(not Path(path).is_absolute() for path in hashes["files"])
    assert all("\\" not in path for path in hashes["files"])
    assert verify_bundle(bundle) == []


def test_build_bundle_refuses_existing_destination_and_secret_manifest_keys(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()

    with pytest.raises(BundleError, match="exists"):
        build_bundle(job, workspace, out_dir)

    with pytest.raises(BundleError, match="credential|secret"):
        build_bundle(_job(params={"api_key": "sk-xyz"}), workspace, tmp_path / "other")


def test_build_bundle_rejects_symlinked_package_inputs_when_supported(tmp_path: Path) -> None:
    job = _job()
    workspace = tmp_path / "workspace"
    package_dir = workspace / "package"
    package_dir.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    try:
        os.symlink(outside, package_dir / "hero.png")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    (package_dir / "hero.pal").write_text("JASC-PAL\r\n0100\r\n1\r\n0 0 0\r\n", encoding="ascii")
    write_report(workspace / "report.json", build_report(job, [], _lineage()))
    write_json_atomic(
        workspace / "lineage.json", [node.model_dump(mode="json") for node in _lineage()]
    )

    with pytest.raises(BundleError, match="symlink|unsafe|reparse"):
        build_bundle(job, workspace, tmp_path / "bundle")


def test_build_bundle_enforces_resource_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, workspace = _workspace(tmp_path)
    import fecreator.reporting.bundle as bundle_module

    monkeypatch.setattr(bundle_module, "MAX_BUNDLE_FILE_COUNT", 1)

    with pytest.raises(BundleError, match="file count|limit"):
        build_bundle(job, workspace, tmp_path / "bundle")


def test_build_bundle_cleans_staging_after_partial_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, workspace = _workspace(tmp_path)
    import fecreator.reporting.bundle as bundle_module

    original_copy = bundle_module._copy_regular_file

    def fail_once(src: Path, dst: Path) -> None:
        if src.name == "hero.pal":
            raise OSError("copy failed halfway")
        original_copy(src, dst)

    monkeypatch.setattr(bundle_module, "_copy_regular_file", fail_once)

    with pytest.raises(OSError, match="halfway"):
        build_bundle(job, workspace, tmp_path / "bundle")

    assert not (tmp_path / "bundle").exists()
    assert not any(
        path.name.startswith(bundle_module.STAGING_PREFIX) for path in tmp_path.iterdir()
    )


def test_verify_bundle_detects_tampered_missing_and_extra_files(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    (bundle / "package" / "hero.png").write_bytes(b"tampered")
    (bundle / "package" / "hero.pal").unlink()
    (bundle / "package" / "extra.txt").write_text("extra", encoding="utf-8")

    codes = {diagnostic.code for diagnostic in verify_bundle(bundle)}

    assert "BUNDLE_HASH_MISMATCH" in codes
    assert "BUNDLE_MISSING_FILE" in codes
    assert "BUNDLE_EXTRA_FILE" in codes


def test_verify_bundle_rejects_unsafe_hash_entries(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    hashes["files"]["../evil.txt"] = "a" * 64
    write_json_atomic(bundle / "hashes.json", hashes)

    assert any(diagnostic.code == "BUNDLE_UNSAFE_PATH" for diagnostic in verify_bundle(bundle))


def test_febuilder_compat_report_preserves_diagnostics_without_claiming_cli_proof(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "package"
    write_valid_package(package_dir)
    (package_dir / "hero.pal").unlink()
    diagnostics = validate_package(package_dir)

    report = febuilder_compat_report(diagnostics)

    assert report["validated_by_cli"] is False
    assert report["source"] == "canonical_gba_validation"
    assert report["errors"] >= 1
    assert "MISSING_PALETTE" in report["codes"]
    assert report["diagnostics"][0]["severity"] in {"error", "warning", "info"}
    assert report["diagnostics"][0]["where"] is not None
