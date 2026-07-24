import io
import json
from pathlib import Path

import pytest

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


def test_serve_binds_exactly_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve command must call uvicorn.run with host='127.0.0.1'."""
    import uvicorn

    captured: list[dict[str, object]] = []

    def fake_run(app: object, *, host: str, port: int, **kwargs: object) -> None:
        captured.append({"host": host, "port": port})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    out = io.StringIO()
    err = io.StringIO()
    rc = run(_app(tmp_path), ["serve"], out, err)
    assert rc == 0, f"serve returned {rc}, stderr: {err.getvalue()}"
    assert len(captured) == 1
    assert captured[0]["host"] == "127.0.0.1"


def test_error_messages_do_not_contain_absolute_paths(tmp_path: Path) -> None:
    """Errors on CLI must not echo absolute filesystem paths in stderr."""
    import re

    out = io.StringIO()
    err = io.StringIO()
    # Trigger a NOT_FOUND error (missing job)
    run(_app(tmp_path), ["job", "status", "nonexistent"], out, err)
    err_text = err.getvalue()
    # Should have an error in stderr
    assert err_text.strip()
    # Must NOT contain a Windows-style absolute path
    assert not re.search(r"[A-Za-z]:\\", err_text), f"path leaked: {err_text!r}"
