"""Bounded external-process boundary tests.

The dangerous case is a child that spawns a grandchild which *inherits* the
captured stdout pipe: killing only the direct child leaves the pipe open, so a
naive drain blocks forever and the "bounded" timeout is not bounded at all.
These tests prove the whole tree is terminated and that every call returns
within a bound even when a survivor holds the pipe.
"""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest

from fecreator.core.process import run_bounded_process, safe_subprocess_env
from tests.fixtures.process_probe import kill_pid, process_is_alive, wait_until_gone

_SPAWNER = """
import json
import os
import subprocess
import sys
import time
from pathlib import Path

grandchild_script = sys.argv[1]
pid_file = Path(sys.argv[2])
marker = Path(sys.argv[3])
own_sleep = float(sys.argv[4])

# No stdout/stderr redirection: the grandchild inherits this process' pipes.
proc = subprocess.Popen([sys.executable, grandchild_script, str(marker)])
pid_file.write_text(
    json.dumps({"child": os.getpid(), "grandchild": proc.pid}), encoding="utf-8"
)
sys.stdout.write("spawned\\n")
sys.stdout.flush()
time.sleep(own_sleep)
sys.stdout.write("child finished\\n")
sys.stdout.flush()
"""

_GRANDCHILD = """
import sys
import time
from pathlib import Path

marker = Path(sys.argv[1])
sys.stdout.write("grandchild alive\\n")
sys.stdout.flush()
time.sleep(120)
marker.write_text("grandchild finished", encoding="utf-8")
"""

_ECHO = """
import sys

payload = sys.stdin.read()
sys.stdout.write("stdout:" + payload)
sys.stderr.write("stderr-detail")
raise SystemExit(int(sys.argv[1]))
"""

_FLOOD = """
import sys

sys.stdout.write("x" * 400000)
sys.stderr.write("y" * 400000)
"""


def _script(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8", newline="\n")
    return path


def _tree_argv(tmp_path: Path, own_sleep: float) -> tuple[list[str], Path, Path]:
    spawner = _script(tmp_path, "spawner.py", _SPAWNER)
    grandchild = _script(tmp_path, "grandchild.py", _GRANDCHILD)
    pid_file = tmp_path / "pids.json"
    marker = tmp_path / "grandchild-finished.txt"
    argv = [
        sys.executable,
        str(spawner),
        str(grandchild),
        str(pid_file),
        str(marker),
        str(own_sleep),
    ]
    return argv, pid_file, marker


def _pids(pid_file: Path) -> tuple[int, int]:
    payload = json.loads(pid_file.read_text(encoding="utf-8"))
    return int(payload["child"]), int(payload["grandchild"])


def test_timeout_terminates_the_whole_process_tree_within_a_bound(tmp_path: Path) -> None:
    argv, pid_file, marker = _tree_argv(tmp_path, own_sleep=120.0)

    started = time.monotonic()
    result = run_bounded_process(
        argv,
        timeout=2.0,
        drain_timeout=2.0,
        env=safe_subprocess_env(),
    )
    elapsed = time.monotonic() - started

    child_pid, grandchild_pid = _pids(pid_file)
    try:
        assert result.timed_out is True
        assert result.returncode is None
        assert elapsed < 20.0
        assert b"spawned" in result.stdout
        assert wait_until_gone(child_pid), "direct child survived the bounded timeout"
        assert wait_until_gone(grandchild_pid), "grandchild survived the bounded timeout"
        assert not marker.exists()
    finally:
        kill_pid(grandchild_pid)
        kill_pid(child_pid)


def test_returns_promptly_when_a_survivor_holds_the_inherited_pipe(tmp_path: Path) -> None:
    argv, pid_file, marker = _tree_argv(tmp_path, own_sleep=0.0)

    started = time.monotonic()
    result = run_bounded_process(
        argv,
        timeout=30.0,
        drain_timeout=1.0,
        env=safe_subprocess_env(),
    )
    elapsed = time.monotonic() - started

    _, grandchild_pid = _pids(pid_file)
    try:
        assert result.timed_out is False
        assert result.returncode == 0
        assert elapsed < 15.0, "draining an inherited pipe must not block on the survivor"
        assert process_is_alive(grandchild_pid)
        assert not marker.exists()
    finally:
        kill_pid(grandchild_pid)
        assert wait_until_gone(grandchild_pid)


def test_captures_streams_exit_code_and_stdin(tmp_path: Path) -> None:
    argv = [sys.executable, str(_script(tmp_path, "echo.py", _ECHO)), "3"]

    result = run_bounded_process(
        argv,
        input_bytes=b"payload",
        timeout=30.0,
        env=safe_subprocess_env(),
    )

    assert result.timed_out is False
    assert result.returncode == 3
    assert result.stdout == b"stdout:payload"
    assert result.stderr == b"stderr-detail"


def test_capture_is_bounded_without_deadlocking_the_child(tmp_path: Path) -> None:
    argv = [sys.executable, str(_script(tmp_path, "flood.py", _FLOOD))]

    result = run_bounded_process(
        argv,
        timeout=30.0,
        max_capture_bytes=1024,
        env=safe_subprocess_env(),
    )

    assert result.timed_out is False
    assert result.returncode == 0
    assert len(result.stdout) == 1024
    assert len(result.stderr) == 1024


def test_rejects_non_positive_bounds(tmp_path: Path) -> None:
    argv = [sys.executable, "-c", "pass"]

    with pytest.raises(ValueError):
        run_bounded_process(argv, timeout=0.0)
    with pytest.raises(ValueError):
        run_bounded_process(argv, timeout=1.0, drain_timeout=-1.0)
    with pytest.raises(ValueError):
        run_bounded_process(argv, timeout=1.0, max_capture_bytes=0)


def test_missing_executable_raises_oserror(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        run_bounded_process([str(tmp_path / "absent binary.exe")], timeout=5.0)
