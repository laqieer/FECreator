from __future__ import annotations

from pathlib import Path

from fecreator.contracts.lineage import LineageNode
from fecreator.core.atomicio import _path_lock, _read_json_unlocked, _write_json_atomic_unlocked
from fecreator.core.paths import ensure_storage_id_not_reserved, normalize_storage_id, safe_join


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
        normalized = normalize_storage_id(asset_id, field_name="asset_id")
        ensure_storage_id_not_reserved(
            normalized,
            field_name="asset_id",
            reserved_values=frozenset({"graph"}),
        )
        safe_join(self._lineage_dir(), f"{normalized}.json")
        return normalized

    def _path(self, asset_id: str) -> Path:
        return safe_join(self._root, "lineage", f"{self._normalize_asset_id(asset_id)}.json")

    def _lock_target(self, asset_id: str) -> Path:
        return safe_join(self._root, "lineage", ".locks", self._normalize_asset_id(asset_id))

    def _lock_path(self, asset_id: str) -> Path:
        return self._lock_target(asset_id).with_suffix(".lock")

    def _graph_lock_target(self) -> Path:
        return safe_join(self._root, "lineage", ".locks", "graph")

    def _graph_lock_path(self) -> Path:
        return self._graph_lock_target().with_suffix(".lock")

    def _read_node_unlocked(self, asset_id: str) -> LineageNode:
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

    def _read_node_locked(self, asset_id: str) -> LineageNode:
        return self._read_node_unlocked(asset_id)

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

    def _normalized_parents(self, parents: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(self._normalize_asset_id(parent) for parent in parents)
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate parent ids are not allowed")
        return normalized

    def add(self, node: LineageNode) -> None:
        """Append a lineage node with caller-provided metadata and output hashes.

        Upstream ingestion owns immutable file copies and hash computation. This
        store validates graph integrity and persists the supplied metadata only.
        """

        asset_id = self._normalize_asset_id(node.asset_id)
        parents = self._normalized_parents(node.parents)
        with _path_lock(self._graph_lock_target(), lock_path=self._graph_lock_path()):
            if self._path(asset_id).exists():
                self._read_node_unlocked(asset_id)
                raise ValueError(f"asset_id already exists: {asset_id}")
            if asset_id in parents:
                raise CycleError(f"self-parent: {asset_id}")
            for parent in parents:
                try:
                    self._read_node_unlocked(parent)
                except FileNotFoundError as exc:
                    raise ValueError(f"unknown parent: {parent}") from exc
            normalized_node = node.model_copy(update={"asset_id": asset_id, "parents": parents})
            _write_json_atomic_unlocked(
                self._path(asset_id),
                normalized_node.model_dump(mode="json"),
            )

    def discard_pending(self, asset_id: str) -> None:
        """Remove a just-created node while compensating a failed publication.

        This is only for rolling back the current transaction before a job is
        durably published; callers must not use it to mutate completed lineage.
        """

        normalized = self._normalize_asset_id(asset_id)
        with _path_lock(self._graph_lock_target(), lock_path=self._graph_lock_path()):
            self._path(normalized).unlink(missing_ok=True)

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
