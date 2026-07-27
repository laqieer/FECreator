"""Optional, safe adapter for an external FEBuilderGBA-compatible CLI.

This is *supplementary* evidence only. The mandatory, CI-safe compatibility
proof is the deterministic ROM-free roundtrip in
:mod:`fecreator.interop.febuilder_roundtrip`; nothing here may weaken, replace,
or stand in for it. When no CLI is configured the adapter reports an explicit
``not_run`` status rather than silently skipping a check.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from fecreator.core.paths import is_contained
from fecreator.core.process import bounded_redacted_text, run_bounded_process, safe_subprocess_env
from fecreator.core.redaction import redact_paths

FeBuilderCommand = Literal["validate-asset", "roundtrip-asset"]
FeBuilderStatus = Literal["not_run", "passed", "failed"]

CLI_ENV_VAR = "FEBUILDER_CLI"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_OUTPUT_CHARS = 4096
ASSET_KIND = "portrait-package"

_COMMANDS: frozenset[str] = frozenset(get_args(FeBuilderCommand))
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_UTF8_SEQUENCE_BYTES = 3

# Fixed, path-free failure text. External diagnostics are bounded and redacted;
# these messages never carry argv, absolute paths, or credentials.
_MISSING_EXECUTABLE = "febuilder cli executable was not found or is not executable"
_UNDECODABLE_OUTPUT = "febuilder cli produced output that is not valid utf-8"
_START_FAILED = "febuilder cli could not be started"


class FeBuilderCliError(Exception):
    """Raised when the adapter is asked to run against unsafe or invalid inputs."""


class FeBuilderCliResult(BaseModel):
    """Bounded, redacted outcome of one optional external CLI invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FeBuilderStatus
    command: FeBuilderCommand
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


def normalize_cli_argv(cli: Sequence[str] | str | Path | None) -> tuple[str, ...]:
    """Normalize configuration into argv without ever splitting a shell string.

    A ``str`` or ``Path`` is one executable token, so paths containing spaces
    (``C:\\Program Files\\FEBuilder\\fe builder.exe``) stay intact. A sequence is
    used verbatim, which is the only way to configure interpreter-style
    invocations such as ``("mono", "FEBuilder.exe")``.
    """
    if cli is None:
        return ()
    if isinstance(cli, str | Path):
        token = str(cli).strip()
        _reject_null(token)
        return (token,) if token else ()
    argv = tuple(str(token) for token in cli)
    if any(not token for token in argv):
        raise FeBuilderCliError("febuilder cli argv contains an empty token")
    for token in argv:
        _reject_null(token)
    return argv


def _reject_null(token: str) -> None:
    """Refuse NUL early, where it is a configuration error, not a ``ValueError``.

    ``subprocess`` and every ``Path`` operation raise a bare
    ``ValueError: embedded null byte`` for these, which would escape this
    adapter as an unhandled exception instead of a stated refusal.
    """
    if "\x00" in token:
        raise FeBuilderCliError("febuilder cli configuration contains a null character")


def febuilder_cli_from_env(env: Mapping[str, str] | None = None) -> tuple[str, ...] | None:
    """Read the opt-in ``FEBUILDER_CLI`` executable path as a single token.

    Returns ``None`` when unset or blank so callers stay in the explicit
    ``not_run`` state. The value is never shell-split, so multi-token
    invocations must be configured through the API instead.
    """
    source = os.environ if env is None else env
    argv = normalize_cli_argv(source.get(CLI_ENV_VAR))
    return argv or None


def build_argv(
    cli_argv: Sequence[str],
    command: FeBuilderCommand,
    package_dir: Path,
    expect_dir: Path | None = None,
) -> list[str]:
    """Build the exact FEBuilder-compatible argv for one asset check."""
    argv = [
        *cli_argv,
        f"--{command}",
        f"--kind={ASSET_KIND}",
        f"--path={package_dir}",
    ]
    if expect_dir is not None:
        argv.append(f"--expect={expect_dir}")
    return argv


def run_febuilder_cli(
    cli: Sequence[str] | str | Path | None,
    command: FeBuilderCommand,
    package_dir: Path,
    expect_dir: Path | None = None,
    *,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
) -> FeBuilderCliResult:
    """Run an optional external FEBuilder-compatible check on a package directory.

    The process is started with ``shell=False`` and an allowlisted environment
    and is bounded by ``timeout_seconds``. On expiry the whole process *tree* is
    terminated by PID and the drain is bounded, so a descendant that inherited
    the captured pipes can neither survive nor block the call. Output is bounded
    and redacted before it leaves this function, so no absolute path or
    credential-shaped value can reach a report or bundle.

    Unsafe or invalid inputs (unknown command, missing/irregular directory,
    symlinked directory, or a path outside ``root``) raise
    :class:`FeBuilderCliError` instead of degrading into a success-shaped
    result. Missing configuration returns ``not_run``; a nonzero exit, timeout,
    unreadable output, or unusable executable returns ``failed``.
    """
    if command not in _COMMANDS:
        raise FeBuilderCliError("unsupported febuilder cli command")
    if expect_dir is not None and command != "roundtrip-asset":
        raise FeBuilderCliError("an expected package directory requires roundtrip-asset")
    if timeout_seconds <= 0:
        raise FeBuilderCliError("febuilder cli timeout must be positive")
    if max_output_chars <= 0:
        raise FeBuilderCliError("febuilder cli output bound must be positive")

    resolved_root = root.resolve() if root is not None else None
    checked_package = _checked_directory(package_dir, resolved_root, label="package")
    checked_expect = (
        _checked_directory(expect_dir, resolved_root, label="expected package")
        if expect_dir is not None
        else None
    )

    cli_argv = normalize_cli_argv(cli)
    if not cli_argv:
        return FeBuilderCliResult(status="not_run", command=command)

    argv = build_argv(cli_argv, command, checked_package, checked_expect)
    try:
        outcome = run_bounded_process(
            argv,
            timeout=timeout_seconds,
            env=safe_subprocess_env(env),
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return _failure(command, _MISSING_EXECUTABLE)
    except (OSError, ValueError):
        return _failure(command, _START_FAILED)

    if outcome.timed_out:
        return _failure(command, f"febuilder cli timed out after {timeout_seconds:.3f}s")

    # Every path this adapter itself put on the command line is redacted by
    # exact value first: generic scrubbing is heuristic, and an unusual spelling
    # (a space, an escaped separator) must not let a known path survive.
    known_paths = (
        *cli_argv,
        str(checked_package),
        *((str(checked_expect),) if checked_expect is not None else ()),
    )

    try:
        stdout_text = _decode(outcome.stdout)
        stderr_text = _decode(outcome.stderr)
    except UnicodeDecodeError:
        return _failure(command, _UNDECODABLE_OUTPUT)

    stdout = _bounded_safe_text(stdout_text, known_paths, max_output_chars)
    stderr = _bounded_safe_text(stderr_text, known_paths, max_output_chars)
    return FeBuilderCliResult(
        status="passed" if outcome.returncode == 0 else "failed",
        command=command,
        exit_code=outcome.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _bounded_safe_text(text: str, known_paths: Sequence[str], limit: int) -> str:
    return bounded_redacted_text(redact_paths(text, known_paths), limit)


def _failure(command: FeBuilderCommand, message: str) -> FeBuilderCliResult:
    return FeBuilderCliResult(status="failed", command=command, stderr=message)


def _decode(raw: bytes | None) -> str:
    """Strictly decode captured output.

    Output is captured as bytes and decoded here rather than by
    ``subprocess``' text mode, because the platform reader threads swallow a
    decode error and would silently turn unreadable output into empty,
    success-shaped output. A multi-byte character cut in half by the capture
    bound is not malformed output, so only a trailing partial sequence is
    dropped; anything else still fails loudly.
    """
    if not raw:
        return ""
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        if exc.start >= len(raw) - _MAX_UTF8_SEQUENCE_BYTES and exc.end >= len(raw):
            return raw[: exc.start].decode("utf-8", errors="strict")
        raise


def _checked_directory(candidate: Path, root: Path | None, *, label: str) -> Path:
    """Resolve one directory argument and refuse anything unsafe to hand over."""
    _reject_null(str(candidate))
    if _is_reparse_point(candidate) or candidate.is_symlink():
        raise FeBuilderCliError(f"{label} directory must not be a link")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise FeBuilderCliError(f"{label} directory does not exist") from exc
    if not resolved.is_dir():
        raise FeBuilderCliError(f"{label} directory is not a directory")
    if root is not None and not is_contained(root, resolved):
        raise FeBuilderCliError(f"{label} directory is outside the allowed root")
    return resolved


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except (OSError, ValueError):
        return False
    return bool(attributes & _REPARSE_POINT)
