from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fecreator.contracts.lineage import LineageNode
from fecreator.contracts.review import CandidateSnapshot
from fecreator.core.atomicio import _fsync_directory
from fecreator.core.paths import safe_join
from fecreator.jobs.candidates import CandidateStore
from fecreator.lineage.store import LineageStore


@dataclass
class CandidatePublication:
    snapshot: CandidateSnapshot
    lineage: LineageNode
    staged_root: Path
    candidate_published: bool = field(init=False, default=False)
    lineage_published: bool = field(init=False, default=False)

    def publish(self, workspace: Path) -> None:
        publish_candidate_atomically(workspace, self.snapshot, self.lineage, self.staged_root)
        self.candidate_published = True
        self.lineage_published = True

    def rollback(self, workspace: Path) -> None:
        rollback_candidate_publication(
            workspace,
            self.lineage.asset_id,
            self.staged_root,
            candidate_published=self.candidate_published,
            lineage_published=self.lineage_published,
        )


def publish_candidate_atomically(
    workspace: Path,
    snapshot: CandidateSnapshot,
    lineage: LineageNode,
    staged_root: Path,
) -> None:
    candidate_root = safe_join(workspace, "candidate")
    if candidate_root.exists():
        raise FileExistsError(f"candidate already exists for job {snapshot.job_id}")
    data_root = workspace.parents[1]
    moved = False
    lineage_created = False
    try:
        os.replace(staged_root, candidate_root)
        moved = True
        _fsync_directory(workspace)
        CandidateStore(data_root).create_while_job_locked(snapshot)
        LineageStore(data_root).add(lineage)
        lineage_created = True
    except Exception as exc:
        try:
            rollback_candidate_publication(
                workspace,
                lineage.asset_id,
                staged_root,
                candidate_published=moved,
                lineage_published=lineage_created,
            )
        except Exception as cleanup_exc:
            raise cleanup_exc from exc
        raise


def rollback_candidate_publication(
    workspace: Path,
    lineage_id: str,
    staged_root: Path,
    *,
    candidate_published: bool,
    lineage_published: bool,
) -> None:
    if candidate_published:
        _remove_tree(safe_join(workspace, "candidate"))
    if lineage_published:
        LineageStore(workspace.parents[1]).discard_pending(lineage_id)
    _remove_tree(staged_root)


def _remove_tree(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
