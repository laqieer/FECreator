from __future__ import annotations

from fecreator.jobs.events import EventLog


def test_append_assigns_monotonic_seq(data_root) -> None:
    log = EventLog(data_root)

    first = log.append("j1", "created", "job created")
    second = log.append("j1", "transition", "created->planning", {"to": "planning"})

    assert (first.seq, second.seq) == (0, 1)
    assert second.data == {"to": "planning"}


def test_read_returns_all_events(data_root) -> None:
    log = EventLog(data_root)
    log.append("j1", "created", "a")
    log.append("j1", "transition", "b")

    events = log.read("j1")

    assert [event.kind for event in events] == ["created", "transition"]


def test_read_missing_job_is_empty(data_root) -> None:
    assert EventLog(data_root).read("nope") == []
