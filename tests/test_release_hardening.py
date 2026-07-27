"""Release hardening regressions found in the final pre-merge review.

Each test pins one place where a failure could have been published, silently
truncated, or accidentally packaged.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import cast

import pytest

from fecreator.contracts.diagnostics import error
from fecreator.contracts.manifest import Manifest
from fecreator.core.clock import utc_now_iso
from fecreator.interop.febuilder_roundtrip import RoundtripEvidence
from fecreator.jobs.model import Job, JobState
from fecreator.reporting.bundle import BundleError, build_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="fake",
    )


def _job() -> Job:
    now = utc_now_iso()
    return Job(
        id="bundle-job",
        state=JobState.COMPLETED,
        manifest=_manifest(),
        revision=1,
        created_at=now,
        updated_at=now,
    )


def _failed_evidence() -> RoundtripEvidence:
    return RoundtripEvidence(
        ok=False,
        dimensions=(128, 112),
        color_count=0,
        background_index=-1,
        pixel_sha256="0" * 64,
        roundtrip_pixel_sha256="1" * 64,
        palette_sha256="2" * 64,
        roundtrip_palette_sha256="3" * 64,
        diagnostics=(error("ROUNDTRIP_DECODE_FAILED", "roundtrip decode failed"),),
    )


def test_build_bundle_refuses_to_publish_a_failed_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fecreator.reporting.bundle as bundle_module

    workspace = tmp_path / "jobs" / "bundle-job"
    (workspace / "package").mkdir(parents=True)
    (workspace / "package" / "hero.png").write_bytes(b"not-a-real-png")
    (workspace / "report.json").write_text("{}", encoding="utf-8")
    (workspace / "lineage.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(bundle_module, "decode_roundtrip", lambda package_dir: _failed_evidence())

    with pytest.raises(BundleError, match="roundtrip"):
        build_bundle(_job(), workspace, tmp_path / "bundle")

    assert not (tmp_path / "bundle").exists()


def test_provider_stdin_write_survives_a_partial_os_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``os.write`` may accept fewer bytes than offered; the rest must follow."""
    import fecreator.core.process as process_module

    read_fd, write_fd = os.pipe()
    payload = b"x" * 4096
    real_write = os.write
    calls: list[int] = []

    def partial_write(fd: int, data: bytes) -> int:
        if fd != write_fd:
            return real_write(fd, data)
        chunk = data[:7]
        calls.append(len(data))
        return real_write(fd, chunk)

    monkeypatch.setattr(process_module.os, "write", partial_write)
    writer = process_module._FdWriter(write_fd, payload)
    try:
        received = b""
        while len(received) < len(payload):
            chunk = real_write and os.read(read_fd, 4096)
            if not chunk:
                break
            received += chunk
    finally:
        writer.finish(5.0)
        os.close(read_fd)

    assert received == payload
    assert len(calls) > 1


@pytest.mark.parametrize(
    "pattern",
    ["/build", "/.pytest-build-probe-*", "/.pytest-editable-probe-*"],
)
def test_packaging_excludes_generated_probe_and_build_directories(pattern: str) -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    hatch_build = cast(dict[str, object], config["tool"])
    excludes = cast(
        list[str],
        cast(dict[str, object], cast(dict[str, object], hatch_build["hatch"])["build"])["exclude"],
    )

    assert pattern in excludes
