from __future__ import annotations

import threading

import pytest

from fecreator.jobs.events import EventLog


def test_append_assigns_monotonic_seq(data_root) -> None:
    log = EventLog(data_root)

    first = log.append("j1", "created", "job created")
    second = log.append("j1", "transition", "created->planning", {"to": "planning"})

    assert (first.seq, second.seq) == (0, 1)
    assert second.data == {"to": "planning"}


def test_append_serializes_concurrent_seq_assignment(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = EventLog(data_root)
    log.append("j1", "created", "job created")
    first_read_started = threading.Event()
    release_first_writer = threading.Event()
    original_read = EventLog.read
    errors: list[Exception] = []
    call_count = 0
    count_lock = threading.Lock()

    def fake_read(self: EventLog, job_id: str):
        nonlocal call_count
        rows = original_read(self, job_id)
        with count_lock:
            call_count += 1
            current_call = call_count
        if current_call == 1:
            first_read_started.set()
            if not release_first_writer.wait(timeout=5):
                raise TimeoutError("timed out waiting to release writer")
        return rows

    def worker(kind: str) -> None:
        try:
            log.append("j1", kind, kind)
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            errors.append(exc)

    monkeypatch.setattr(EventLog, "read", fake_read)

    first = threading.Thread(target=worker, args=("planning",))
    second = threading.Thread(target=worker, args=("processing",))
    first.start()
    if first_read_started.wait(timeout=1):
        second.start()
        release_first_writer.set()
    else:
        second.start()
    first.join(timeout=5)
    second.join(timeout=5)
    release_first_writer.set()

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert [event.seq for event in log.read("j1")] == [0, 1, 2]


def test_read_returns_all_events(data_root) -> None:
    log = EventLog(data_root)
    log.append("j1", "created", "a")
    log.append("j1", "transition", "b")

    events = log.read("j1")

    assert [event.kind for event in events] == ["created", "transition"]


def test_read_missing_job_is_empty(data_root) -> None:
    assert EventLog(data_root).read("nope") == []
