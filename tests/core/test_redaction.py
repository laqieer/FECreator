from __future__ import annotations

from fecreator.core.redaction import contains_secret_key, redact


def test_redact_masks_tokens() -> None:
    redacted = redact("authorization: Bearer sk-abc123 token=sk-abc123 sig=xyz")

    assert "***" in redacted
    assert "sk-abc123" not in redacted
    assert "xyz" not in redacted


def test_contains_secret_key() -> None:
    assert contains_secret_key("api_key") is True
    assert contains_secret_key("authorization") is True
    assert contains_secret_key("width") is False
