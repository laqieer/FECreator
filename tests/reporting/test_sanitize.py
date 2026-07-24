from __future__ import annotations

from fecreator.reporting.sanitize import sanitize_text


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
