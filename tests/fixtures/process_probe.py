"""Cross-platform liveness probes for tests that must prove a process is gone.

``os.kill(pid, 0)`` is not a liveness probe on Windows: CPython implements
``os.kill`` there with ``TerminateProcess``, so signalling would *cause* the
outcome the test claims to observe.  The Windows branch therefore queries the
process exit code through ``kernel32`` and never touches the process.
"""

from __future__ import annotations

import os
import subprocess
import time
from contextlib import suppress
from pathlib import Path

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_is_alive(pid: int) -> bool:
    """Return whether ``pid`` is still running, without disturbing it."""
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - alive but owned by another user
        return True
    return True


def _windows_process_is_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):  # pragma: no cover
            return False
        return bool(code.value == _STILL_ACTIVE)
    finally:
        kernel32.CloseHandle(handle)


def wait_until_gone(pid: int, timeout: float = 15.0) -> bool:
    """Poll until ``pid`` disappears, returning whether it did within ``timeout``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            return True
        time.sleep(0.05)
    return not process_is_alive(pid)


def kill_pid(pid: int) -> None:
    """Best-effort cleanup so no test process outlives its test."""
    if not process_is_alive(pid):
        return
    if os.name == "nt":
        taskkill = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run(
            [str(taskkill), "/F", "/PID", str(pid)],
            capture_output=True,
            shell=False,
            check=False,
            timeout=15,
        )
        return

    import signal

    with suppress(OSError):  # pragma: no cover - already gone
        os.kill(pid, signal.SIGKILL)
