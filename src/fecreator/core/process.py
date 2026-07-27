from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fecreator.core.redaction import redact

_COMMON_SAFE_ENV_KEYS = frozenset({"PATH", "PYTHONIOENCODING"})
_POSIX_SAFE_ENV_KEYS = frozenset(
    {"DYLD_LIBRARY_PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "LD_LIBRARY_PATH", "TMPDIR"}
)
_WINDOWS_SAFE_ENV_KEYS = frozenset(
    {"COMSPEC", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "WINDIR"}
)

TRUNCATION_SUFFIX = "... [truncated]"

DEFAULT_DRAIN_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_CAPTURE_BYTES = 1 << 20
_READ_CHUNK_BYTES = 65536
_TASKKILL_TIMEOUT_SECONDS = 15.0
_SIGTERM_GRACE_SECONDS = 0.5


def safe_subprocess_env(
    source_env: Mapping[str, str] | None = None,
    *,
    os_name: str | None = None,
) -> dict[str, str]:
    """Build the allowlisted environment handed to any external process.

    Only the keys required to start a process on the current platform are
    forwarded, so provider credentials and other ambient configuration never
    reach a third-party executable.
    """
    env_source = source_env or os.environ
    safe_env = {"PYTHONIOENCODING": env_source.get("PYTHONIOENCODING", "utf-8")}
    allowed = set(_COMMON_SAFE_ENV_KEYS)
    if (os_name or os.name) == "nt":
        allowed.update(_WINDOWS_SAFE_ENV_KEYS)
    else:
        allowed.update(_POSIX_SAFE_ENV_KEYS)

    for key in sorted(allowed):
        if key == "PYTHONIOENCODING":
            continue
        value = env_source.get(key)
        if value:
            safe_env[key] = value
    return safe_env


def bounded_redacted_text(text: str | None, limit: int) -> str:
    """Redact external output and bound it before it reaches any report."""
    if not text:
        return ""

    redacted = redact(text.strip())
    if len(redacted) <= limit:
        return redacted
    return f"{redacted[:limit]}{TRUNCATION_SUFFIX}"


@dataclass(frozen=True)
class BoundedProcessResult:
    """Outcome of one bounded external process run.

    ``returncode`` is ``None`` exactly when ``timed_out`` is true: a process the
    boundary had to terminate has no meaningful exit status. ``stdout`` and
    ``stderr`` always hold whatever was captured before the bound elapsed, so a
    timeout still yields partial diagnostics.
    """

    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool


def run_bounded_process(
    argv: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    timeout: float,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    drain_timeout: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
    max_capture_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
) -> BoundedProcessResult:
    """Run one external process with a genuinely bounded wall-clock cost.

    ``subprocess.run(timeout=...)`` is not sufficient here. It kills only the
    direct child and then drains the captured pipes, so a grandchild that
    inherited stdout keeps the pipe open and the "bounded" call blocks forever.
    This boundary instead:

    * starts the child in its own POSIX session (process group) or Windows
      process group, so the whole tree can be addressed;
    * captures stdout/stderr through raw OS pipes drained by daemon threads,
      which removes the classic pipe-buffer deadlock and lets a pipe still held
      by a survivor be *abandoned* rather than waited on (a Python buffered
      stream cannot be abandoned: closing it blocks on the buffer lock held by
      the reader);
    * terminates the *tree* by PID on expiry (``killpg`` on POSIX,
      ``taskkill /T /F /PID`` on Windows -- never a name-based kill); and
    * bounds the post-kill drain.

    ``shell=False`` is fixed and ``argv`` is always passed as a list, so no
    caller can introduce shell interpretation.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if drain_timeout < 0:
        raise ValueError("drain timeout must not be negative")
    if max_capture_bytes <= 0:
        raise ValueError("max capture bytes must be positive")

    creation_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        creation_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        creation_kwargs["start_new_session"] = True

    stdin_read, stdin_write = os.pipe()
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    child_fds = (stdin_read, stdout_write, stderr_write)
    try:
        proc = subprocess.Popen(
            list(argv),
            stdin=stdin_read,
            stdout=stdout_write,
            stderr=stderr_write,
            shell=False,
            env=dict(env) if env is not None else None,
            cwd=str(cwd) if cwd is not None else None,
            **creation_kwargs,
        )
    except BaseException:
        for fd in (*child_fds, stdin_write, stdout_read, stderr_read):
            _close_fd(fd)
        raise

    # The parent's copies of the child-side ends must go, or the read ends
    # would never see EOF even after the whole tree exits.
    for fd in child_fds:
        _close_fd(fd)

    writer = _FdWriter(stdin_write, input_bytes)
    stdout_reader = _FdReader(stdout_read, max_capture_bytes)
    stderr_reader = _FdReader(stderr_read, max_capture_bytes)

    timed_out = False
    try:
        returncode: int | None = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = None
        terminate_process_tree(proc, timeout=drain_timeout)

    writer.finish(drain_timeout)
    stdout_reader.finish(drain_timeout)
    stderr_reader.finish(drain_timeout)

    return BoundedProcessResult(
        returncode=None if timed_out else returncode,
        stdout=stdout_reader.data(),
        stderr=stderr_reader.data(),
        timed_out=timed_out,
    )


def terminate_process_tree(
    proc: subprocess.Popen[bytes],
    *,
    timeout: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
) -> None:
    """Terminate a child *and its descendants*, addressing them only by PID.

    Killing the direct child is not enough: descendants inherit the captured
    pipes and keep them open. Termination is always PID-scoped; no image-name
    based mechanism is used, so an unrelated process sharing a program name can
    never be killed.
    """
    if sys.platform == "win32":
        _terminate_windows_tree(proc, timeout)
    else:
        _terminate_posix_group(proc, timeout)


def _terminate_posix_group(proc: subprocess.Popen[bytes], timeout: float) -> None:
    if sys.platform == "win32":  # pragma: no cover - platform guard for type narrowing
        return
    # The child was started with start_new_session=True, so its process group
    # id equals its pid and the group outlives the leader while members remain.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with suppress(OSError):
            os.killpg(proc.pid, sig)
        try:
            proc.wait(timeout=max(_SIGTERM_GRACE_SECONDS, min(timeout, 2.0)))
        except subprocess.TimeoutExpired:
            continue
        if sig is signal.SIGTERM:
            # The leader is reaped; still SIGKILL the group so no descendant
            # keeps the inherited pipes open.
            with suppress(OSError):
                os.killpg(proc.pid, signal.SIGKILL)
        return


def _terminate_windows_tree(proc: subprocess.Popen[bytes], timeout: float) -> None:
    if sys.platform != "win32":  # pragma: no cover - platform guard for type narrowing
        return
    taskkill = _taskkill_path()
    if taskkill is not None:
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [str(taskkill), "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                shell=False,
                check=False,
                timeout=_TASKKILL_TIMEOUT_SECONDS,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
    with suppress(OSError):
        proc.kill()
    with suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=max(_SIGTERM_GRACE_SECONDS, min(timeout, 5.0)))


def _taskkill_path() -> Path | None:
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or r"C:\Windows"
    candidate = Path(system_root) / "System32" / "taskkill.exe"
    return candidate if candidate.is_file() else None


def _close_fd(fd: int) -> None:
    with suppress(OSError):  # pragma: no cover - already closed
        os.close(fd)


class _FdReader:
    """Drain one raw pipe fd on a daemon thread, keeping at most ``limit`` bytes.

    Reading concurrently keeps a chatty child from blocking on a full pipe
    buffer. The fd is deliberately left open when the drain bound elapses: a
    descendant still holds the write end, so closing it here is either
    impossible to do safely or would block, and abandoning one fd is the price
    of a call that always returns.
    """

    def __init__(self, fd: int, limit: int) -> None:
        self._fd = fd
        self._limit = limit
        self._chunks: list[bytes] = []
        self._size = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while True:
                chunk = os.read(self._fd, _READ_CHUNK_BYTES)
                if not chunk:
                    return
                with self._lock:
                    if self._size < self._limit:
                        self._chunks.append(chunk[: self._limit - self._size])
                        self._size += len(chunk)
        except OSError:  # pragma: no cover - pipe closed under us
            return

    def finish(self, timeout: float) -> None:
        self._thread.join(timeout)
        if not self._thread.is_alive():
            _close_fd(self._fd)

    def data(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)


class _FdWriter:
    """Feed stdin on a daemon thread so a stalled child cannot block the caller."""

    def __init__(self, fd: int, payload: bytes | None) -> None:
        self._fd = fd
        self._payload = payload
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            if self._payload:
                os.write(self._fd, self._payload)
        except OSError:
            pass
        finally:
            _close_fd(self._fd)

    def finish(self, timeout: float) -> None:
        self._thread.join(timeout)
