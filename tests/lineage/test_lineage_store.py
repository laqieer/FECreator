from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fecreator.contracts.lineage import LineageNode, Operation, Region
from fecreator.core.paths import PathEscapeError
from fecreator.lineage.store import CycleError, LineageCorruptionError, LineageStore

SRC_DIR = Path(__file__).resolve().parents[2] / "src"


def _node(
    asset_id: str,
    parents: tuple[str, ...] = (),
    op: Operation = Operation.CREATE_NEUTRAL,
    **changes: object,
) -> LineageNode:
    payload: dict[str, object] = {
        "asset_id": asset_id,
        "operation": op,
        "parents": parents,
        "provider": "synthetic-provider",
        "model": "synthetic-model",
        "prompt": "synthetic prompt",
        "reference_pack": "marth",
        "reference_pack_rev": 2,
        "seed": 1234,
        "params": {"cfg_scale": 7, "seed_locked": True},
        "mask": "masks/smile.png",
        "protected_regions": (Region(x=0, y=0, w=48, h=32, label="eyes"),),
        "metrics": {"score": 0.95},
        "approved_by": "reviewer",
        "output_hashes": ("a" * 64, "b" * 64),
        "created_at": "2026-07-24T00:00:00+00:00",
    }
    payload.update(changes)
    return LineageNode(**payload)


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SRC_DIR) if not env.get("PYTHONPATH") else f"{SRC_DIR}{os.pathsep}{env['PYTHONPATH']}"
    )
    return env


def test_add_and_get_preserves_metadata(data_root: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("root"))

    loaded = store.get("root")

    assert loaded.operation is Operation.CREATE_NEUTRAL
    assert loaded.reference_pack_rev == 2
    assert loaded.protected_regions[0].label == "eyes"
    assert loaded.output_hashes == ("a" * 64, "b" * 64)
    with pytest.raises(TypeError):
        loaded.params["cfg_scale"] = 8


def test_ancestors_and_children_are_deterministic(data_root: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("a"))
    store.add(_node("b", parents=("a",), op=Operation.REFINE_EXPRESSION))
    store.add(_node("c", parents=("a",), op=Operation.VARIANT_MASKED_EDIT))
    store.add(_node("d", parents=("b", "c"), op=Operation.EXPORT_SPEC))

    assert [node.asset_id for node in store.ancestors("d")] == ["b", "c", "a"]
    assert [node.asset_id for node in store.children("a")] == ["b", "c"]


def test_duplicate_asset_id_raises(data_root: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("a"))

    with pytest.raises(ValueError, match="already exists"):
        store.add(_node("a", op=Operation.IMPORT_CONCEPT))


def test_unknown_parent_raises(data_root: Path) -> None:
    store = LineageStore(data_root)

    with pytest.raises(ValueError, match="unknown parent"):
        store.add(_node("b", parents=("missing",)))


def test_self_parent_is_cycle(data_root: Path) -> None:
    store = LineageStore(data_root)

    with pytest.raises(CycleError, match="self-parent"):
        store.add(_node("a", parents=("a",)))


def test_duplicate_parent_ids_raise(data_root: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("a"))

    with pytest.raises(ValueError, match="duplicate parent"):
        store.add(_node("b", parents=("a", "a")))


@pytest.mark.parametrize(
    "asset_id",
    [
        ".",
        "..",
        ".locks",
        ".hidden",
        "graph",
        "locks",
        ".tmp-hidden",
        " a",
        "a ",
        "a/b",
        "a\\b",
    ],
)
def test_asset_id_rejects_reserved_or_ambiguous_values(data_root: Path, asset_id: str) -> None:
    store = LineageStore(data_root)

    with pytest.raises(ValueError):
        store.add(_node(asset_id))


def test_absolute_asset_id_raises_path_escape(data_root: Path) -> None:
    store = LineageStore(data_root)

    with pytest.raises(PathEscapeError):
        store.add(_node("C:\\escape"))


def test_get_raises_for_corrupt_visible_node(data_root: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("a"))
    (data_root / "lineage" / "a.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(LineageCorruptionError, match="corrupt"):
        store.get("a")


def test_children_raise_for_corrupt_visible_record(data_root: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("a"))
    store.add(_node("b", parents=("a",)))
    (data_root / "lineage" / "broken.json").write_text("{}", encoding="utf-8")

    with pytest.raises(LineageCorruptionError, match="corrupt"):
        store.children("a")


def test_concurrent_add_allows_only_one_winner_for_same_asset_id(
    data_root: Path,
    tmp_path: Path,
) -> None:
    script = tmp_path / "add_lineage_node.py"
    script.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path

from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.lineage.store import LineageStore


result_path = Path(sys.argv[2])
try:
    LineageStore(Path(sys.argv[1])).add(
        LineageNode(
            asset_id="asset-1",
            operation=Operation.CREATE_NEUTRAL,
            created_at="2026-07-24T00:00:00+00:00",
        )
    )
    result_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
except Exception as exc:
    result_path.write_text(
        json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}),
        encoding="utf-8",
    )
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    first_result = tmp_path / "add-1.json"
    second_result = tmp_path / "add-2.json"

    first = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(first_result)],
        env=_worker_env(),
    )
    second = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(second_result)],
        env=_worker_env(),
    )
    first.wait(timeout=10)
    second.wait(timeout=10)

    results = [
        json.loads(first_result.read_text(encoding="utf-8")),
        json.loads(second_result.read_text(encoding="utf-8")),
    ]
    assert sum(result["ok"] for result in results) == 1
    assert sum(not result["ok"] for result in results) == 1
    assert LineageStore(data_root).get("asset-1").asset_id == "asset-1"


def test_concurrent_distinct_children_are_not_lost(data_root: Path, tmp_path: Path) -> None:
    store = LineageStore(data_root)
    store.add(_node("a"))
    script = tmp_path / "add_child.py"
    script.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path

from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.lineage.store import LineageStore


result_path = Path(sys.argv[2])
try:
    LineageStore(Path(sys.argv[1])).add(
        LineageNode(
            asset_id=sys.argv[3],
            operation=Operation.REFINE_EXPRESSION,
            parents=("a",),
            created_at="2026-07-24T00:00:00+00:00",
        )
    )
    result_path.write_text(json.dumps({"ok": True, "asset_id": sys.argv[3]}), encoding="utf-8")
except Exception as exc:
    result_path.write_text(
        json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}),
        encoding="utf-8",
    )
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    first_result = tmp_path / "child-1.json"
    second_result = tmp_path / "child-2.json"

    first = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(first_result), "b"],
        env=_worker_env(),
    )
    second = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(second_result), "c"],
        env=_worker_env(),
    )
    first.wait(timeout=10)
    second.wait(timeout=10)

    results = [
        json.loads(first_result.read_text(encoding="utf-8")),
        json.loads(second_result.read_text(encoding="utf-8")),
    ]
    assert all(result["ok"] for result in results)
    assert [node.asset_id for node in LineageStore(data_root).children("a")] == ["b", "c"]


def test_concurrent_mutual_parent_adds_fail_promptly_with_domain_error(
    data_root: Path,
    tmp_path: Path,
) -> None:
    script = tmp_path / "add_mutual_parent.py"
    script.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path

from fecreator.contracts.lineage import LineageNode, Operation
from fecreator.lineage.store import LineageStore


result_path = Path(sys.argv[2])
try:
    LineageStore(Path(sys.argv[1])).add(
        LineageNode(
            asset_id=sys.argv[3],
            operation=Operation.REFINE_EXPRESSION,
            parents=(sys.argv[4],),
            created_at="2026-07-24T00:00:00+00:00",
        )
    )
    result_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
except Exception as exc:
    result_path.write_text(
        json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}),
        encoding="utf-8",
    )
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    first_result = tmp_path / "mutual-1.json"
    second_result = tmp_path / "mutual-2.json"

    started = time.monotonic()
    first = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(first_result), "a", "b"],
        env=_worker_env(),
    )
    second = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(second_result), "b", "a"],
        env=_worker_env(),
    )
    first.wait(timeout=10)
    second.wait(timeout=10)
    elapsed = time.monotonic() - started

    results = [
        json.loads(first_result.read_text(encoding="utf-8")),
        json.loads(second_result.read_text(encoding="utf-8")),
    ]
    assert elapsed < 2.0
    assert all(not result["ok"] for result in results)
    assert {result["error"] for result in results} == {"ValueError"}
    assert all("unknown parent" in result["message"] for result in results)
