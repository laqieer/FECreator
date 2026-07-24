"""Tests for the GitGuardian/ggshield configuration and pre-commit hook.

These lock in the secret-scanning guardrails: the ggshield config must keep
detection at full strength (no broad ignored paths/detectors, secrets never
printed) while ignoring only the two exact synthetic historical fingerprints,
and the official ggshield pre-commit hook must stay pinned.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITGUARDIAN_CONFIG = REPO_ROOT / ".gitguardian.yaml"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

# The exact synthetic historical match fingerprints that are safe to ignore.
SYNTHETIC_JWT_FINGERPRINT = "66c5e99a80784da68902affa0beae974f17f53c2112fc933137957ab8a92aa07"
SYNTHETIC_AWS_FINGERPRINT = "457643f44d19aed85fd756aa50cc0cd6b57376d4e8f5a72f9f85972a522002a3"

PINNED_GGSHIELD_REV = "v1.52.2"
GGSHIELD_REPO = "https://github.com/GitGuardian/ggshield"


def _gitguardian_config() -> dict:
    return yaml.safe_load(GITGUARDIAN_CONFIG.read_text(encoding="utf-8"))


def _pre_commit_config() -> dict:
    return yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))


def test_gitguardian_config_is_v2() -> None:
    assert _gitguardian_config()["version"] == 2


def test_gitguardian_never_shows_secrets() -> None:
    config = _gitguardian_config()
    assert config["secret"]["show_secrets"] is False
    # Guard against the value ever flipping to true anywhere in the file.
    assert "show_secrets: true" not in GITGUARDIAN_CONFIG.read_text(encoding="utf-8").lower()


def test_gitguardian_does_not_force_exit_zero() -> None:
    assert _gitguardian_config()["exit_zero"] is False


def test_gitguardian_ignores_only_the_two_synthetic_fingerprints() -> None:
    ignored = _gitguardian_config()["secret"]["ignored_matches"]
    fingerprints = {entry["match"] for entry in ignored}
    assert fingerprints == {SYNTHETIC_JWT_FINGERPRINT, SYNTHETIC_AWS_FINGERPRINT}
    # Each ignored match must be clearly named.
    for entry in ignored:
        assert entry.get("name")


def test_gitguardian_ignored_matches_carry_no_plaintext_secret() -> None:
    # Only fingerprints (64 hex chars) are stored, never a plaintext value.
    for entry in _gitguardian_config()["secret"]["ignored_matches"]:
        match = entry["match"]
        assert len(match) == 64
        assert all(c in "0123456789abcdef" for c in match)


def test_gitguardian_does_not_broadly_ignore_paths_or_detectors() -> None:
    secret = _gitguardian_config()["secret"]
    assert not secret.get("ignored_paths")
    assert not secret.get("ignored_detectors")


def test_pre_commit_pins_official_ggshield_hook() -> None:
    repos = _pre_commit_config()["repos"]
    ggshield_repo = next(r for r in repos if r["repo"] == GGSHIELD_REPO)
    assert ggshield_repo["rev"] == PINNED_GGSHIELD_REV
    hook = next(h for h in ggshield_repo["hooks"] if h["id"] == "ggshield")
    assert hook["language_version"] == "python3"
    assert "pre-commit" in hook["stages"]
