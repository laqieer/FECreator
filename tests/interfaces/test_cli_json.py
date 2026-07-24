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
    rc = run(_app(tmp_path), ["validate", "--spec", "fe-gba-portrait-standard",
                              "--path", str(tmp_path)], out)
    codes = {d["code"] for d in json.loads(out.getvalue())}
    assert rc == 2 and "MISSING_SHEET" in codes


def test_job_create_and_status(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "asset_type": "portrait", "target_spec": "fe-gba-portrait-standard",
        "workflow": "text_to_portrait", "provider": "fake",
        "sources": [{"kind": "text", "ref": "hero"}]}))
    out = io.StringIO()
    run(_app(tmp_path), ["job", "create", "--manifest", str(manifest)], out)
    job_id = json.loads(out.getvalue())["id"]
    out2 = io.StringIO()
    run(_app(tmp_path), ["job", "status", job_id], out2)
    assert json.loads(out2.getvalue())["state"] == "created"
