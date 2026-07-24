import io
import json
from pathlib import Path

from fecreator.app import FeCreatorApp
from fecreator.core.config import Settings
from fecreator.interfaces.cli_json import run


def _app(tmp_path: Path) -> FeCreatorApp:
    return FeCreatorApp(Settings(data_root=tmp_path))


def test_list_specs_json(tmp_path: Path) -> None:
    out = io.StringIO()
    rc = run(_app(tmp_path), ["list-specs"], out)
    assert rc == 0
    assert "fe-gba-portrait-standard" in json.loads(out.getvalue())


def test_validate_missing_sheet(tmp_path: Path) -> None:
    out = io.StringIO()
    rc = run(
        _app(tmp_path),
        ["validate", "--spec", "fe-gba-portrait-standard", "--path", str(tmp_path)],
        out,
    )
    codes = {d["code"] for d in json.loads(out.getvalue())}
    assert rc == 2 and "MISSING_SHEET" in codes


def test_validate_unknown_spec_exits_nonzero(tmp_path: Path) -> None:
    out = io.StringIO()
    err = io.StringIO()
    rc = run(
        _app(tmp_path), ["validate", "--spec", "no-such-spec", "--path", str(tmp_path)], out, err
    )
    assert rc != 0
    err_obj = json.loads(err.getvalue())
    assert err_obj["error"] == "SPEC_NOT_FOUND"


def test_job_create_and_status(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "asset_type": "portrait",
                "target_spec": "fe-gba-portrait-standard",
                "workflow": "text_to_portrait",
                "provider": "fake",
                "sources": [{"kind": "text", "ref": "hero"}],
            }
        )
    )
    out = io.StringIO()
    run(_app(tmp_path), ["job", "create", "--manifest", str(manifest)], out)
    job_id = json.loads(out.getvalue())["id"]
    out2 = io.StringIO()
    run(_app(tmp_path), ["job", "status", job_id], out2)
    assert json.loads(out2.getvalue())["state"] == "created"


def test_job_cancel(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "asset_type": "portrait",
                "target_spec": "fe-gba-portrait-standard",
                "workflow": "text_to_portrait",
                "provider": "fake",
                "sources": [],
            }
        )
    )
    out = io.StringIO()
    run(_app(tmp_path), ["job", "create", "--manifest", str(manifest)], out)
    job_id = json.loads(out.getvalue())["id"]
    out2 = io.StringIO()
    rc = run(_app(tmp_path), ["job", "cancel", job_id], out2)
    assert rc == 0
    assert json.loads(out2.getvalue())["state"] == "cancelled"


def test_invalid_state_exits_nonzero(tmp_path: Path) -> None:
    """Cancelling a cancelled job should give a structured error, nonzero exit."""
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "asset_type": "portrait",
                "target_spec": "fe-gba-portrait-standard",
                "workflow": "text_to_portrait",
                "provider": "fake",
                "sources": [],
            }
        )
    )
    out = io.StringIO()
    run(_app(tmp_path), ["job", "create", "--manifest", str(manifest)], out)
    job_id = json.loads(out.getvalue())["id"]
    run(_app(tmp_path), ["job", "cancel", job_id], io.StringIO())
    out2 = io.StringIO()
    err = io.StringIO()
    rc = run(_app(tmp_path), ["job", "cancel", job_id], out2, err)
    assert rc != 0
    err_json = json.loads(err.getvalue())
    assert "error" in err_json


def test_serve_rejects_non_loopback(tmp_path: Path) -> None:
    out = io.StringIO()
    err = io.StringIO()
    rc = run(_app(tmp_path), ["serve", "--host", "0.0.0.0"], out, err)
    assert rc != 0
    assert "UNSAFE_HOST" in err.getvalue()
