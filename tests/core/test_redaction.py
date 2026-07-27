from __future__ import annotations

import json
from pathlib import PureWindowsPath

import pytest

from fecreator.core.redaction import contains_secret_key, redact, redact_paths
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


@pytest.mark.parametrize(
    ("text", "leaked"),
    [
        pytest.param(
            r"opened C:\Program Files\FE Builder\fe builder.exe now",
            (r"C:\Program Files", "Program Files", "FE Builder"),
            id="windows-spaces-standalone",
        ),
        pytest.param(
            'opened "C:\\Program Files\\FE Builder\\fe builder.exe" now',
            (r"C:\Program Files", "Program Files", "FE Builder"),
            id="windows-spaces-quoted",
        ),
        pytest.param(
            r"--path=C:\Users\build agent\pkg with spaces",
            (r"C:\Users", "Users", "build agent"),
            id="windows-spaces-flag",
        ),
        pytest.param(
            "--path=/srv/build agent/pkg with spaces",
            ("/srv", "/srv/build agent", "build agent"),
            id="posix-spaces-flag",
        ),
        pytest.param(
            "scanned /opt/fe builder/private/hero.png today",
            ("/opt/fe builder", "fe builder", "private"),
            id="posix-spaces-standalone",
        ),
        pytest.param(
            r"scanned \\build server\private share\pkg\hero.png today",
            (r"\\build server", "build server", "private share"),
            id="unc-spaces",
        ),
        pytest.param(
            r'{"argv": ["--path=C:\\Users\\build agent\\pkg with spaces"]}',
            (r"C:\\Users", "Users", "build agent"),
            id="json-escaped-windows",
        ),
    ],
)
def test_redact_scrubs_absolute_paths_with_spaces_without_leaking_parents(
    text: str, leaked: tuple[str, ...]
) -> None:
    redacted = redact(text)

    for fragment in leaked:
        assert fragment not in redacted


def test_redact_does_not_glue_trailing_prose_onto_a_path() -> None:
    redacted = redact(r"copied \\server\share\private\hero.png into notes\drafts")

    assert redacted == r"copied hero.png into notes\drafts"


def test_redact_paths_removes_exactly_known_argv_paths() -> None:
    package = PureWindowsPath(r"C:\Users\build agent\pkg with spaces")
    text = f'ran "{package}" and {package} and {json.dumps(str(package))} and {package.as_posix()}'

    redacted = redact_paths(text, [package])

    assert "build agent" not in redacted
    assert r"C:\Users" not in redacted
    assert "C:/Users" not in redacted
    assert redacted.count("pkg with spaces") == 4


def test_contains_secret_key() -> None:
    assert contains_secret_key("api_key") is True
    assert contains_secret_key("authorization") is True
    assert contains_secret_key("MY_API_KEY") is True
    assert contains_secret_key("OPENAI_SECRET") is True
    assert contains_secret_key("X_TOKEN") is True
    assert contains_secret_key("width") is False
    assert contains_secret_key("bandwidth") is False
