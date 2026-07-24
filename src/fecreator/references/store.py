from __future__ import annotations

from pathlib import Path

from fecreator.core.paths import safe_join
from fecreator.references.model import ReferencePack


class ReferencePackStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _pack_dir(self, pack_id: str) -> Path:
        return safe_join(self._root, "references", pack_id)

    def latest(self, pack_id: str) -> ReferencePack | None:
        pack_dir = self._pack_dir(pack_id)
        if not pack_dir.exists():
            return None
        return ReferencePack(id=pack_id, path=pack_dir)
