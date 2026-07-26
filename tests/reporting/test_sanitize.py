from __future__ import annotations

import base64

import pytest

from fecreator.reporting.sanitize import OPAQUE_BASE64_KEYS, sanitize_json, sanitize_text


def test_sanitize_text_redacts_unc_path_substrings_without_mangling_plain_backslashes() -> None:
    text = (
        "copied from \\\\server\\share\\private\\hero.png into notes\\drafts and "
        "left regular \\slashes\\alone"
    )

    sanitized = sanitize_text(text)

    assert "\\\\server\\share\\private\\hero.png" not in sanitized
    assert "hero.png" in sanitized
    assert "notes\\drafts" in sanitized
    assert "regular \\slashes\\alone" in sanitized


def test_opaque_base64_transport_field_is_not_mutated_while_text_is_redacted() -> None:
    payload = {
        "content_base64": base64.b64encode(bytes(range(256))).decode("ascii"),
        "path": "C:\\private\\hero.png",
        "detail": "token=secret-value",
    }

    sanitized = sanitize_json(payload, error_cls=ValueError, opaque_keys=OPAQUE_BASE64_KEYS)

    assert sanitized == {
        "content_base64": payload["content_base64"],
        "detail": "token=***",
        "path": "hero.png",
    }


def test_opaque_key_rejects_values_outside_the_base64_alphabet() -> None:
    with pytest.raises(ValueError, match="base64"):
        sanitize_json(
            {"content_base64": "C:\\private\\hero.png"},
            error_cls=ValueError,
            opaque_keys=OPAQUE_BASE64_KEYS,
        )


def test_opaque_keys_are_not_applied_by_default() -> None:
    sanitized = sanitize_json({"content_base64": "A+/A"}, error_cls=ValueError)

    assert sanitized == {"content_base64": "A+A"}
