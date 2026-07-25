from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.core.config import Settings
from fecreator.interfaces import cli_json


def _app(data_root: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=data_root))


def _manual_manifest() -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow="text_to_portrait",
        provider="manual",
        sources=(SourceSpec(kind="text", ref="hero"),),
    )


def _write_png(path: Path, color: tuple[int, int, int] = (0, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 80), color).save(path, format="PNG")


def test_cli_plan_sources_writes_source_plan_and_waiting_state(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manual_manifest())
    plan_dir = tmp_path / "plan"
    out = io.StringIO()

    rc = cli_json.run(
        app,
        ["plan-sources", "--job", job.id, "--out", str(plan_dir)],
        out,
    )
    payload = json.loads(out.getvalue())

    assert rc == 0
    assert "neutral.png" in payload["expected_filenames"]
    assert json.loads((plan_dir / "source_plan.json").read_text(encoding="utf-8")) == payload
    assert app.get_job(job.id).state.value == "waiting_for_sources"


def test_cli_submit_sources_copies_immutable_snapshot_for_manual_job(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manual_manifest())
    cli_json.run(
        app,
        ["plan-sources", "--job", job.id, "--out", str(tmp_path / "plan")],
        io.StringIO(),
    )
    incoming = tmp_path / "incoming"
    original_source = incoming / "neutral.png"
    _write_png(original_source, color=(10, 20, 30))
    out = io.StringIO()

    rc = cli_json.run(
        app,
        ["submit-sources", "--job", job.id, "--sources", str(incoming)],
        out,
    )
    payload = json.loads(out.getvalue())
    submitted = data_root / "jobs" / job.id / "submitted" / "neutral.png"
    submitted_bytes = submitted.read_bytes()
    _write_png(original_source, color=(200, 10, 10))

    assert rc == 0
    assert payload["state"] == "waiting_for_sources"
    assert submitted.exists()
    assert submitted.read_bytes() == submitted_bytes
    assert submitted.read_bytes() != original_source.read_bytes()
    assert app.get_job(job.id).state.value == "waiting_for_sources"


def test_cli_submit_sources_missing_directory_returns_deterministic_json_error(
    data_root: Path,
    tmp_path: Path,
) -> None:
    app = _app(data_root)
    job = app.create_job(_manual_manifest())
    cli_json.run(
        app,
        ["plan-sources", "--job", job.id, "--out", str(tmp_path / "plan")],
        io.StringIO(),
    )
    missing = tmp_path / "missing"
    out = io.StringIO()

    rc = cli_json.run(
        app,
        ["submit-sources", "--job", job.id, "--sources", str(missing)],
        out,
    )
    payload = json.loads(out.getvalue())

    assert rc == 2
    assert payload[0]["code"] == "SUBMIT_SOURCES_FAILED"
    assert payload[0]["where"] == "missing"
    assert payload[0]["severity"] == "error"
    assert "detail" in payload[0]["data"]
