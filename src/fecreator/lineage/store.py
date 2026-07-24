from __future__ import annotations

from pathlib import Path

from fecreator.contracts.lineage import LineageNode
from fecreator.core.atomicio import _path_lock, _read_json_unlocked, _write_json_atomic_unlocked
from fecreator.core.paths import safe_join


class CycleError(Exception):
    """Raised when adding a node would create a cycle in the lineage DAG."""


class LineageCorruptionError(Exception):
    """Raised when a visible lineage record is missing required data or is malformed."""


class LineageStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _lineage_dir(self) -> Path:
        return safe_join(self._root, "lineage")

    def _normalize_asset_id(self, asset_id: str) -> str:
        normalized = asset_id.strip()
        if not normalized:
            raise ValueError("asset_id must be a non-empty string")
        safe_join(self._lineage_dir(), f"{normalized}.json")
        if "/" in normalized or "\\" in normalized:
            raise ValueError(f"asset_id must not contain path separators: {asset_id!r}")
        return normalized

    def _path(self, asset_id: str) -> Path:
        return safe_join(self._root, "lineage", f"{self._normalize_asset_id(asset_id)}.json")

    def _lock_target(self, asset_id: str) -> Path:
        return safe_join(self._root, "lineage", ".locks", self._normalize_asset_id(asset_id))

    def _lock_path(self, asset_id: str) -> Path:
        return self._lock_target(asset_id).with_suffix(".lock")

    def _read_node_locked(self, asset_id: str) -> LineageNode:
        path = self._path(asset_id)
        try:
            payload = _read_json_unlocked(path)
            node = LineageNode.model_validate(payload)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise LineageCorruptionError(f"corrupt lineage node: {path}") from exc
        if node.asset_id != self._normalize_asset_id(asset_id):
            raise LineageCorruptionError(f"corrupt lineage node: {path}")
        return node

    def _iter_nodes(self) -> list[LineageNode]:
        lineage_dir = self._lineage_dir()
        if not lineage_dir.exists():
            return []

        nodes: list[LineageNode] = []
        for entry in sorted(lineage_dir.iterdir(), key=lambda path: path.name):
            if entry.name.startswith(".") or entry.name.endswith(".tmp"):
                continue
            if entry.is_dir():
                raise LineageCorruptionError(f"unexpected directory in lineage store: {entry}")
            if entry.suffix != ".json":
                raise LineageCorruptionError(f"unexpected file in lineage store: {entry}")
            nodes.append(self.get(entry.stem))
        return nodes

    def add(self, node: LineageNode) -> None:
        asset_id = self._normalize_asset_id(node.asset_id)
        with _path_lock(self._path(asset_id), lock_path=self._lock_path(asset_id)):
            if self._path(asset_id).exists():
                self._read_node_locked(asset_id)
                raise ValueError(f"asset_id already exists: {asset_id}")
            if asset_id in node.parents:
                raise CycleError(f"self-parent: {asset_id}")
            for parent in node.parents:
                try:
                    self.get(parent)
                except FileNotFoundError as exc:
                    raise ValueError(f"unknown parent: {parent}") from exc
            _write_json_atomic_unlocked(self._path(asset_id), node.model_dump(mode="json"))

    def get(self, asset_id: str) -> LineageNode:
        normalized = self._normalize_asset_id(asset_id)
        with _path_lock(self._path(normalized), lock_path=self._lock_path(normalized)):
            return self._read_node_locked(normalized)

    def ancestors(self, asset_id: str) -> list[LineageNode]:
        seen: set[str] = set()
        ordered: list[LineageNode] = []
        frontier = list(self.get(asset_id).parents)
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            node = self.get(current)
            seen.add(current)
            ordered.append(node)
            frontier.extend(node.parents)
        return ordered

    def children(self, asset_id: str) -> list[LineageNode]:
        normalized = self._normalize_asset_id(asset_id)
        self.get(normalized)
        return [node for node in self._iter_nodes() if normalized in node.parents]
