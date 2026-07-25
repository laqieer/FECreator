from __future__ import annotations

import pytest

from fecreator.core.redaction import contains_secret_key, redact
from tests.fixtures.synthetic_secrets import synthetic_aws_key, synthetic_jwt


def test_redact_masks_tokens() -> None:
    redacted = redact("authorization: Bearer sk-abc123 token=sk-abc123 sig=xyz")

    assert "***" in redacted
    assert "sk-abc123" not in redacted
    assert "xyz" not in redacted


def test_redact_masks_bare_tokens_and_embedded_absolute_paths() -> None:
    aws_key = synthetic_aws_key()
    jwt = synthetic_jwt()
    text = (
        "failed reading C:\\secret\\nested\\hero.png and /srv/private/out.png; "
        "retry with sk-live-abc123456789 ghp_abcdefghijklmnopqrstuvwxyz123456 "
        f"{aws_key} {jwt} "
        "while keeping ordinary words"
    )

    redacted = redact(text)

    assert "C:\\secret\\nested\\hero.png" not in redacted
    assert "/srv/private/out.png" not in redacted
    assert "sk-live-abc123456789" not in redacted
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert aws_key not in redacted
    assert jwt not in redacted
    assert "failed reading" in redacted
    assert "ordinary words" in redacted
    assert "***" in redacted


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/pytest-123\\nested\\artifact.png",
        "C:/tmp\\nested\\artifact.png",
        "C:\\tmp\\nested\\artifact.png",
        "\\\\server\\share\\nested\\artifact.png",
        "/var/tmp/nested/artifact.png",
    ],
)
def test_redact_absolute_paths_keep_only_basename(path: str) -> None:
    redacted = redact(f"build exploded at {path}")

    assert redacted == "build exploded at artifact.png"
    assert path not in redacted
    assert "nested" not in redacted


def test_contains_secret_key() -> None:
    assert contains_secret_key("api_key") is True
    assert contains_secret_key("authorization") is True
    assert contains_secret_key("MY_API_KEY") is True
    assert contains_secret_key("OPENAI_SECRET") is True
    assert contains_secret_key("X_TOKEN") is True
    assert contains_secret_key("width") is False
    assert contains_secret_key("bandwidth") is False
