"""Regression guard: no literal JWT or AWS-key shaped secrets in tracked text.

Secret-shaped test fixtures must be assembled at runtime (see
``tests/fixtures/synthetic_secrets.py``) so that scanners never see a literal
credential in the source tree.  This test walks every tracked text file and
fails if a JWT or AWS-access-key literal reappears, guarding against
regressions.  Only generated/vendor/.git paths are excluded -- the test tree
itself is deliberately scanned.

The detection patterns are assembled from fragments so this guard does not
itself embed a scanner-visible literal.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Assembled from fragments so this file contains no pattern-shaped literal.
_JWT_PATTERN = re.compile("ey" + "J" + r"[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}")
_AWS_PATTERN = re.compile("AK" + "IA" + r"[0-9A-Z]{16}")

# Only generated/vendor paths are excluded; the .git directory is never tracked.
_EXCLUDED_PREFIXES = (
    "node_modules/",
    "dist/",
    "build/",
    "src/fecreator/_web/",
)
_EXCLUDED_FILES = ("package-lock.json",)


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True, encoding="utf-8")
    return [line for line in out.splitlines() if line]


def _is_scanned(path: str) -> bool:
    if path in _EXCLUDED_FILES:
        return False
    return not any(path.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def test_no_literal_jwt_or_aws_key_in_tracked_text_files() -> None:
    offenders: list[str] = []
    for rel in _tracked_files():
        if not _is_scanned(rel):
            continue
        file_path = REPO_ROOT / rel
        try:
            text = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _JWT_PATTERN.search(line):
                offenders.append(f"{rel}:{lineno} (JWT-shaped literal)")
            if _AWS_PATTERN.search(line):
                offenders.append(f"{rel}:{lineno} (AWS-key-shaped literal)")

    message = "Literal secret-shaped values found (use runtime builders):\n" + "\n".join(offenders)
    assert not offenders, message
