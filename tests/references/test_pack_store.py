from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fecreator.contracts.result import Artifact
from fecreator.core.paths import PathEscapeError
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackCorruptionError, ReferencePackStore

SRC_DIR = Path(__file__).resolve().parents[2] / "src"


def _artifact(name: str, sha: str) -> Artifact:
    return Artifact(
        role="concept_art",
        path=f"incoming/{name}.png",
        sha256=sha * 64,
        media_type="image/png",
    )


def _pack(pack_id: str = "marth", revision: int = 99, **changes: object) -> ReferencePack:
    payload: dict[str, object] = {
        "id": pack_id,
        "revision": revision,
        "source": "synthetic fixture prompt",
        "concept_art": (_artifact("front", "a"), _artifact("alt", "b")),
        "traits": {"hair": "blue", "weapon": "rapier"},
        "swatches": ("#112233", "#445566"),
        "forbidden_changes": ("change face shape",),
        "provenance": "synthetic-fixture",
        "rights": "original",
    }
    payload.update(changes)
    return ReferencePack(**payload)


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SRC_DIR) if not env.get("PYTHONPATH") else f"{SRC_DIR}{os.pathsep}{env['PYTHONPATH']}"
    )
    return env


def test_create_forces_revision_one_and_preserves_metadata(data_root: Path) -> None:
    store = ReferencePackStore(data_root)

    saved = store.create(_pack())

    assert saved.revision == 1
    assert saved.source == "synthetic fixture prompt"
    assert saved.concept_art[0].sha256 == "a" * 64
    assert saved.traits["hair"] == "blue"
    assert saved.swatches == ("#112233", "#445566")
    with pytest.raises(TypeError):
        saved.traits["hair"] = "green"


def test_new_revision_increments_and_keeps_history(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())

    rev2 = store.new_revision(
        "marth",
        swatches=("#778899",),
        provenance="approved synthetic edit",
    )

    assert rev2.revision == 2
    assert store.get("marth", 1).swatches == ("#112233", "#445566")
    assert store.latest("marth").provenance == "approved synthetic edit"


def test_prior_revision_file_unchanged(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())
    original = (data_root / "refs" / "marth" / "1.json").read_text(encoding="utf-8")

    store.new_revision("marth", rights="licensed")

    assert (data_root / "refs" / "marth" / "1.json").read_text(encoding="utf-8") == original


def test_create_rejects_duplicate_pack_id(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())

    with pytest.raises(ValueError, match="already exists"):
        store.create(_pack())


def test_missing_revision_raises(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())

    with pytest.raises(FileNotFoundError):
        store.get("marth", 5)


@pytest.mark.parametrize(
    "pack_id",
    [
        ".",
        "..",
        ".locks",
        ".hidden",
        "locks",
        ".tmp-hidden",
        " marth",
        "marth ",
        "mar/th",
        "mar\\th",
    ],
)
def test_pack_id_rejects_reserved_or_ambiguous_values(data_root: Path, pack_id: str) -> None:
    store = ReferencePackStore(data_root)

    with pytest.raises(ValueError):
        store.create(_pack(pack_id=pack_id))


def test_absolute_pack_id_raises_path_escape(data_root: Path) -> None:
    store = ReferencePackStore(data_root)

    with pytest.raises(PathEscapeError):
        store.create(_pack(pack_id="C:\\escape"))


def test_latest_raises_for_missing_visible_revision(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())
    (data_root / "refs" / "marth" / "3.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ReferencePackCorruptionError, match="missing revision"):
        store.latest("marth")


def test_get_raises_for_corrupt_visible_revision(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())
    (data_root / "refs" / "marth" / "1.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ReferencePackCorruptionError, match="corrupt"):
        store.get("marth", 1)


def test_concurrent_create_allows_only_one_winner(data_root: Path, tmp_path: Path) -> None:
    script = tmp_path / "create_pack.py"
    script.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path

from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack
from fecreator.references.store import ReferencePackStore


def build_pack() -> ReferencePack:
    return ReferencePack(
        id="marth",
        revision=99,
        source="synthetic fixture prompt",
        concept_art=(
            Artifact(
                role="concept_art",
                path="incoming/front.png",
                sha256="a" * 64,
                media_type="image/png",
            ),
        ),
        traits={"hair": "blue"},
        swatches=("#112233",),
        forbidden_changes=("change face shape",),
        provenance="synthetic-fixture",
        rights="original",
    )


result_path = Path(sys.argv[2])
try:
    saved = ReferencePackStore(Path(sys.argv[1])).create(build_pack())
    result_path.write_text(
        json.dumps({"ok": True, "revision": saved.revision}),
        encoding="utf-8",
    )
except Exception as exc:
    result_path.write_text(
        json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}),
        encoding="utf-8",
    )
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    first_result = tmp_path / "create-1.json"
    second_result = tmp_path / "create-2.json"

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
    store = ReferencePackStore(data_root)
    assert store.latest("marth").revision == 1


def test_concurrent_new_revision_assigns_unique_revisions(
    data_root: Path,
    tmp_path: Path,
) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())
    script = tmp_path / "revise_pack.py"
    script.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path

from fecreator.references.store import ReferencePackStore


result_path = Path(sys.argv[2])
try:
    saved = ReferencePackStore(Path(sys.argv[1])).new_revision(
        "marth",
        provenance=sys.argv[3],
    )
    result_path.write_text(
        json.dumps(
            {"ok": True, "revision": saved.revision, "provenance": saved.provenance}
        ),
        encoding="utf-8",
    )
except Exception as exc:
    result_path.write_text(
        json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}),
        encoding="utf-8",
    )
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    first_result = tmp_path / "revision-1.json"
    second_result = tmp_path / "revision-2.json"

    first = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(first_result), "worker-1"],
        env=_worker_env(),
    )
    second = subprocess.Popen(
        [sys.executable, str(script), str(data_root), str(second_result), "worker-2"],
        env=_worker_env(),
    )
    first.wait(timeout=10)
    second.wait(timeout=10)

    results = [
        json.loads(first_result.read_text(encoding="utf-8")),
        json.loads(second_result.read_text(encoding="utf-8")),
    ]
    assert all(result["ok"] for result in results)
    assert sorted(result["revision"] for result in results) == [2, 3]
    assert {store.get("marth", 2).provenance, store.get("marth", 3).provenance} == {
        "worker-1",
        "worker-2",
    }


def test_latest_and_new_revision_handle_double_digit_revisions(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())

    for index in range(2, 12):
        created = store.new_revision("marth", provenance=f"worker-{index}")
        assert created.revision == index

    assert store.latest("marth").revision == 11
    assert store.new_revision("marth", provenance="worker-12").revision == 12


def test_double_digit_gap_raises_contiguity_error(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())
    for index in range(2, 12):
        store.new_revision("marth", provenance=f"worker-{index}")

    (data_root / "refs" / "marth" / "10.json").unlink()

    with pytest.raises(ReferencePackCorruptionError, match="missing revision"):
        store.latest("marth")


def test_init_prunes_only_stale_reference_staging_directories(data_root: Path) -> None:
    refs_dir = data_root / "refs"
    refs_dir.mkdir()
    stale = refs_dir / ".tmp-stale"
    fresh = refs_dir / ".tmp-fresh"
    stale.mkdir()
    fresh.mkdir()
    now = time.time()
    os.utime(stale, (now - 600, now - 600))
    os.utime(fresh, (now, now))

    ReferencePackStore(data_root)

    assert not stale.exists()
    assert fresh.exists()


def test_init_keeps_stale_reference_staging_directory_with_active_lock(
    data_root: Path,
    tmp_path: Path,
) -> None:
    refs_dir = data_root / "refs"
    staging = refs_dir / ".tmp-active"
    staging.mkdir(parents=True)
    now = time.time() - 600
    os.utime(staging, (now, now))
    script = tmp_path / "hold_stage_lock.py"
    script.write_text(
        """
from __future__ import annotations

import sys
import time
from pathlib import Path

from fecreator.core.atomicio import _path_lock


target = Path(sys.argv[1])
ready = Path(sys.argv[2])
with _path_lock(target, timeout=5.0, poll_interval=0.01):
    ready.write_text("ready", encoding="utf-8")
    time.sleep(1.0)
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    ready = tmp_path / "ready.txt"
    holder = subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(data_root / "refs" / ".locks" / "staging-active"),
            str(ready),
        ],
        env=_worker_env(),
    )
    try:
        deadline = time.time() + 5
        while not ready.exists():
            assert time.time() < deadline
            time.sleep(0.01)

        ReferencePackStore(data_root)
    finally:
        holder.wait(timeout=5)

    assert staging.exists()


def test_create_requires_explicit_non_empty_provenance_and_rights(data_root: Path) -> None:
    store = ReferencePackStore(data_root)

    with pytest.raises(ValueError, match="provenance"):
        store.create(_pack(provenance=""))

    with pytest.raises(ValueError, match="rights"):
        store.create(_pack(rights=" "))


def test_new_revision_rejects_blank_provenance_and_rights(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())

    with pytest.raises(ValueError, match="provenance"):
        store.new_revision("marth", provenance="")

    with pytest.raises(ValueError, match="rights"):
        store.new_revision("marth", rights=" ")


def test_get_preserves_legacy_empty_provenance_and_rights(data_root: Path) -> None:
    store = ReferencePackStore(data_root)
    store.create(_pack())
    legacy_path = data_root / "refs" / "marth" / "2.json"
    legacy_payload = {
        **store.get("marth", 1).model_dump(mode="json"),
        "revision": 2,
        "provenance": "",
        "rights": "",
    }
    legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    loaded = store.get("marth", 2)

    assert loaded.provenance == ""
    assert loaded.rights == ""
