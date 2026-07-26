from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact, StageResult
from fecreator.core.atomicio import LockTimeoutError, write_json_atomic
from fecreator.core.hashing import sha256_file
from fecreator.interop.febuilder_roundtrip import decode_roundtrip
from fecreator.jobs.model import Job, JobState
from fecreator.reporting.bundle import (
    BundleError,
    build_bundle,
    febuilder_compat_report,
    verify_bundle,
)
from fecreator.reporting.json_report import build_report, write_report
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


def _lineage(output_hashes: tuple[str, ...]) -> list[LineageNode]:
    return [
        LineageNode(
            asset_id="asset-a",
            operation=Operation.EXPORT_SPEC,
            provider="fake",
            output_hashes=output_hashes,
            created_at="2026-07-24T00:02:00+00:00",
        )
    ]


def _workspace(tmp_path: Path, *, job: Job | None = None) -> tuple[Job, Path]:
    active_job = job or _job()
    workspace = tmp_path / "workspace"
    package_dir = workspace / "package"
    write_valid_package(package_dir)
    output_hashes = (
        sha256_file(package_dir / "hero.pal"),
        sha256_file(package_dir / "hero.png"),
    )
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
                        sha256=sha256_file(package_dir / "hero.png"),
                        media_type="image/png",
                    ),
                    Artifact(
                        role="palette",
                        path="package\\hero.pal",
                        sha256=sha256_file(package_dir / "hero.pal"),
                        media_type="text/plain",
                    ),
                ),
            )
        ],
        _lineage(output_hashes),
    )
    write_report(workspace / "report.json", report)
    write_json_atomic(
        workspace / "lineage.json",
        [node.model_dump(mode="json") for node in _lineage(output_hashes)],
    )
    return active_job, workspace


def _bundle_worker_script(tmp_path: Path) -> Path:
    script = tmp_path / "bundle_worker.py"
    script.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            import json
            import sys
            import time
            from pathlib import Path

            from fecreator.jobs.model import Job
            from fecreator.reporting.bundle import BundleError, build_bundle


            def main() -> int:
                start = Path(sys.argv[1])
                workspace = Path(sys.argv[2])
                out_dir = Path(sys.argv[3])
                payload = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
                while not start.exists():
                    time.sleep(0.01)
                try:
                    build_bundle(Job.model_validate(payload), workspace, out_dir)
                except BundleError as exc:
                    print(exc)
                    return 2
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ).strip()
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return script


def test_build_bundle_publishes_canonical_files_and_relative_hashes(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)

    bundle = build_bundle(job, workspace, tmp_path / "bundle")

    assert bundle == tmp_path / "bundle"
    assert (bundle / "manifest.json").exists()
    assert (bundle / "report.json").exists()
    assert (bundle / "lineage.json").exists()
    assert (bundle / "hashes.json").exists()
    assert (bundle / "compat.json").exists()
    assert (bundle / "package" / "hero.png").exists()
    assert (bundle / "package" / "hero.pal").exists()

    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert list(hashes["files"]) == sorted(hashes["files"])
    assert all(not Path(path).is_absolute() for path in hashes["files"])
    assert all("\\" not in path for path in hashes["files"])
    assert report["stages"][0]["artifacts"][1]["path"] == "package/hero.png"
    assert report["output_hashes"] == sorted(
        {
            sha256_file(bundle / "package" / "hero.png"),
            sha256_file(bundle / "package" / "hero.pal"),
        }
    )
    compat = json.loads((bundle / "compat.json").read_text(encoding="utf-8"))
    assert compat["source"] == "deterministic_febuilder_compatible_roundtrip"
    assert compat["validated_by_cli"] is False
    assert compat["roundtrip"]["ok"] is True
    assert compat["roundtrip"]["pixel_sha256"] == compat["roundtrip"]["roundtrip_pixel_sha256"]
    assert compat["roundtrip"]["palette_sha256"] == compat["roundtrip"]["roundtrip_palette_sha256"]
    assert str(tmp_path) not in json.dumps(compat)
    assert verify_bundle(bundle) == []


def test_bundle_roundtrip_evidence_is_reproducible_across_workspaces(tmp_path: Path) -> None:
    first_job, first_workspace = _workspace(tmp_path / "first")
    second_job, second_workspace = _workspace(tmp_path / "second")

    first_bundle = build_bundle(first_job, first_workspace, tmp_path / "first-bundle")
    second_bundle = build_bundle(second_job, second_workspace, tmp_path / "second-bundle")

    assert (first_bundle / "compat.json").read_bytes() == (
        second_bundle / "compat.json"
    ).read_bytes()
    assert (first_bundle / "hashes.json").read_bytes() == (
        second_bundle / "hashes.json"
    ).read_bytes()


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
    output_hashes = ("a" * 64, "b" * 64)
    write_report(workspace / "report.json", build_report(job, [], _lineage(output_hashes)))
    write_json_atomic(
        workspace / "lineage.json",
        [node.model_dump(mode="json") for node in _lineage(output_hashes)],
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


@pytest.mark.parametrize(
    ("path_key", "where"),
    [
        ("C:/evil.txt", "C:/evil.txt"),
        ("//server/share.txt", "//server/share.txt"),
        ("\\\\server\\share.txt", "\\\\server\\share.txt"),
        ("package\\hero.png", "package\\hero.png"),
        ("/etc/passwd", "/etc/passwd"),
    ],
)
def test_verify_bundle_normalizes_unsafe_declarations_to_diagnostics(
    tmp_path: Path, path_key: str, where: str
) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    hashes["files"][path_key] = "a" * 64
    write_json_atomic(bundle / "hashes.json", hashes)

    diagnostics = verify_bundle(bundle)

    assert any(
        diagnostic.code == "BUNDLE_UNSAFE_PATH" and diagnostic.where == where
        for diagnostic in diagnostics
    )


def test_verify_bundle_reports_cross_file_inconsistencies(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    report["manifest_hash"] = "f" * 64
    report["lineage"] = []
    report["output_hashes"] = ["0" * 64]
    write_json_atomic(bundle / "report.json", report)

    codes = {diagnostic.code for diagnostic in verify_bundle(bundle)}

    assert "BUNDLE_INCONSISTENT_MANIFEST_HASH" in codes
    assert "BUNDLE_INCONSISTENT_LINEAGE" in codes
    assert "BUNDLE_INCONSISTENT_OUTPUT_HASHES" in codes


def test_verify_bundle_requires_valid_deterministic_roundtrip_evidence(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    compat = json.loads((bundle / "compat.json").read_text(encoding="utf-8"))
    compat["roundtrip"]["ok"] = False
    write_json_atomic(bundle / "compat.json", compat)

    codes = {diagnostic.code for diagnostic in verify_bundle(bundle)}

    assert "BUNDLE_HASH_MISMATCH" in codes
    assert "BUNDLE_COMPAT_FAILURE" in codes


def test_verify_bundle_rejects_missing_or_invalid_roundtrip_evidence(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    (bundle / "compat.json").unlink()

    diagnostics = verify_bundle(bundle)

    assert any(
        diagnostic.code == "BUNDLE_MISSING_FILE" and diagnostic.where == "compat.json"
        for diagnostic in diagnostics
    )


def test_verify_bundle_sanitizes_missing_root_where(tmp_path: Path) -> None:
    missing = tmp_path / "missing-bundle"

    diagnostics = verify_bundle(missing)

    assert diagnostics[0].code == "BUNDLE_MISSING_ROOT"
    assert diagnostics[0].where == "missing-bundle"
    assert str(tmp_path) not in diagnostics[0].where


def test_verify_bundle_detects_casefold_collisions(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    bundle = build_bundle(job, workspace, tmp_path / "bundle")
    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    hashes["files"]["package/HERO.png"] = hashes["files"]["package/hero.png"]
    write_json_atomic(bundle / "hashes.json", hashes)

    diagnostics = verify_bundle(bundle)

    assert any(diagnostic.code == "BUNDLE_UNSAFE_PATH" for diagnostic in diagnostics)


def test_build_bundle_serializes_cross_process_writers(tmp_path: Path) -> None:
    job, workspace = _workspace(tmp_path)
    script = _bundle_worker_script(tmp_path)
    payload_path = tmp_path / "job.json"
    payload_path.write_text(json.dumps(job.model_dump(mode="json")), encoding="utf-8")
    start = tmp_path / "start.txt"
    out_dir = tmp_path / "bundle"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")

    first = subprocess.Popen(
        [sys.executable, str(script), str(start), str(workspace), str(out_dir), str(payload_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    second = subprocess.Popen(
        [sys.executable, str(script), str(start), str(workspace), str(out_dir), str(payload_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    time.sleep(0.1)
    start.write_text("go", encoding="utf-8")
    first_stdout, first_stderr = first.communicate(timeout=30)
    second_stdout, second_stderr = second.communicate(timeout=30)

    assert sorted([first.returncode, second.returncode]) == [0, 2]
    assert (out_dir / "manifest.json").exists()
    assert verify_bundle(out_dir) == []
    assert not any(path.name.startswith(".bundle-stage-") for path in tmp_path.iterdir())
    loser_output = "\n".join(
        part for part in (first_stdout, first_stderr, second_stdout, second_stderr) if part
    )
    assert "refusing to overwrite" in loser_output or "already exists" in loser_output


def test_build_bundle_translates_lock_timeout_to_bundle_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, workspace = _workspace(tmp_path)
    import fecreator.reporting.bundle as bundle_module

    lock_error = LockTimeoutError(
        f"timed out acquiring lock for {tmp_path}\\bundle via {tmp_path}\\.bundle.lock"
    )

    @contextmanager
    def fail_lock(*args: object, **kwargs: object):
        raise lock_error
        yield

    monkeypatch.setattr(bundle_module, "_path_lock", fail_lock)

    with pytest.raises(BundleError, match="busy|lock|contention") as exc_info:
        build_bundle(job, workspace, tmp_path / "bundle")

    assert exc_info.value.__cause__ is lock_error
    assert str(tmp_path) not in str(exc_info.value)


def test_febuilder_compat_report_preserves_diagnostics_without_claiming_cli_proof(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "package"
    write_valid_package(package_dir)
    (package_dir / "hero.pal").unlink()
    evidence = decode_roundtrip(package_dir)

    report = febuilder_compat_report(evidence)

    assert report["validated_by_cli"] is False
    assert report["source"] == "deterministic_febuilder_compatible_roundtrip"
    assert report["roundtrip"]["ok"] is False
    assert report["errors"] >= 1
    assert "MISSING_PALETTE" in report["codes"]
    assert report["diagnostics"][0]["severity"] in {"error", "warning", "info"}
    assert report["diagnostics"][0]["where"] is not None
