from __future__ import annotations

import json
from pathlib import Path

import pytest

from fecreator.contracts.diagnostics import error
from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact, StageResult
from fecreator.jobs.model import Job, JobState
from fecreator.reporting.json_report import build_report, write_report
from tests.fixtures.synthetic_secrets import synthetic_aws_key, synthetic_jwt


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
        revision=3,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:01:00+00:00",
    )


def _lineage(asset_id: str, *, prompt: str | None = None, created_at: str) -> LineageNode:
    return LineageNode(
        asset_id=asset_id,
        operation=Operation.EXPORT_SPEC,
        provider="fake",
        prompt=prompt,
        output_hashes=("b" * 64, "a" * 64),
        created_at=created_at,
    )


def _stage(stage: str, *, path: str, secret_value: str = "token=plain") -> StageResult:
    return StageResult(
        stage=stage,
        ok=True,
        artifacts=(
            Artifact(
                role=f"{stage}-sheet",
                path=path,
                sha256=f"{stage[0]}" * 64,
                media_type="image/png",
            ),
        ),
        diagnostics=(
            error(
                f"{stage.upper()}_WARN",
                "signed url leaked? https://example.test/file.png?sig=abc123",
                where="C:\\sensitive\\hero.png",
                data={"detail": secret_value},
            ),
        ),
    )


def test_build_report_contains_manifest_hash_stages_lineage_and_output_hashes() -> None:
    report = build_report(
        _job(),
        [
            _stage("validate", path="package\\hero.png"),
            _stage("assemble", path="C:\\workspace\\package\\hero.png"),
        ],
        [
            _lineage("asset-b", created_at="2026-07-24T00:03:00+00:00"),
            _lineage(
                "asset-a",
                created_at="2026-07-24T00:02:00+00:00",
                prompt="authorization: Bearer sk-live-secret",
            ),
        ],
    )

    assert report["job_id"] == "job-1"
    assert report["manifest_hash"] == _job().manifest.content_hash()
    assert [stage["stage"] for stage in report["stages"]] == ["assemble", "validate"]
    assert report["stages"][0]["artifacts"][0]["path"] == "hero.png"
    assert report["stages"][1]["artifacts"][0]["path"] == "package/hero.png"
    assert report["diagnostics"][0]["where"] == "hero.png"
    assert report["lineage"][0]["asset_id"] == "asset-a"
    assert report["output_hashes"] == sorted(
        {
            "a" * 64,
            "b" * 64,
            "a" * 64,
            "v" * 64,
        }
    )


def test_build_report_refuses_secret_key_names_and_redacts_nested_strings() -> None:
    aws_key = synthetic_aws_key()
    jwt = synthetic_jwt()

    with pytest.raises(ValueError, match="credential|secret"):
        build_report(_job(params={"api_key": "sk-xyz"}), [], [])

    report = build_report(
        _job(params={"note": "keep sk-live-abc123456789 and ghp_abcdefghijklmnopqrstuvwxyz123456"}),
        [
            _stage(
                "export",
                path="package\\hero.png",
                secret_value=f"{aws_key} {jwt}",
            )
        ],
        [
            _lineage(
                "asset-a",
                prompt=(
                    "read C:\\secret\\nested\\hero.png and /srv/private/out.png "
                    "before using signature=secret"
                ),
                created_at="2026-07-24T00:02:00+00:00",
            )
        ],
    )

    payload = json.dumps(report, sort_keys=True)
    assert "sk-live-abc123456789" not in payload
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in payload
    assert aws_key not in payload
    assert jwt not in payload
    assert "signature=secret" not in payload
    assert "C:\\secret\\nested\\hero.png" not in payload
    assert "/srv/private/out.png" not in payload
    assert "package\\hero.png" not in payload
    assert "package/hero.png" in payload
    assert "***" in payload


def test_write_report_is_deterministic_for_equivalent_inputs(tmp_path: Path) -> None:
    report_a = build_report(
        _job(),
        [_stage("validate", path="package\\hero.png"), _stage("assemble", path="hero.png")],
        [
            _lineage("asset-b", created_at="2026-07-24T00:03:00+00:00"),
            _lineage("asset-a", created_at="2026-07-24T00:02:00+00:00"),
        ],
    )
    report_b = build_report(
        _job(),
        [_stage("assemble", path="hero.png"), _stage("validate", path="package\\hero.png")],
        [
            _lineage("asset-a", created_at="2026-07-24T00:02:00+00:00"),
            _lineage("asset-b", created_at="2026-07-24T00:03:00+00:00"),
        ],
    )

    path_a = tmp_path / "report-a.json"
    path_b = tmp_path / "report-b.json"
    write_report(path_a, report_a)
    write_report(path_b, report_b)

    assert path_a.read_bytes() == path_b.read_bytes()
    assert b"\r\n" not in path_a.read_bytes()
