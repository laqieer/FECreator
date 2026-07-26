from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_job_import_can_precede_candidate_snapshot_import_in_clean_subprocess() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from fecreator.jobs.model import Job\n"
                "from fecreator.contracts.review import CandidateSnapshot\n"
                "print(Job.__name__)\n"
                "print(CandidateSnapshot.__name__)\n"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["Job", "CandidateSnapshot"]
