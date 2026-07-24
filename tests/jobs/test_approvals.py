from __future__ import annotations

import threading

import pytest

from fecreator.jobs.approvals import ApprovalError, ApprovalStore


def test_approve_and_read(data_root) -> None:
    store = ApprovalStore(data_root)

    record = store.approve(" j1 ", " neutral ", " alice ")

    assert record.decision == "approved"
    assert record.actor == "alice"
    assert [decision.stage for decision in store.decisions("j1")] == ["neutral"]


def test_concurrent_decisions_do_not_allow_duplicates(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ApprovalStore(data_root)
    first_check_started = threading.Event()
    release_first_writer = threading.Event()
    original_decisions = ApprovalStore.decisions
    errors: list[Exception] = []
    call_count = 0
    count_lock = threading.Lock()

    def fake_decisions(self: ApprovalStore, job_id: str):
        nonlocal call_count
        rows = original_decisions(self, job_id)
        with count_lock:
            call_count += 1
            current_call = call_count
        if current_call == 1:
            first_check_started.set()
            if not release_first_writer.wait(timeout=5):
                raise TimeoutError("timed out waiting to release writer")
        return rows

    def approve() -> None:
        try:
            store.approve("j1", "neutral", "alice")
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            errors.append(exc)

    def reject() -> None:
        try:
            store.reject("j1", "neutral", "bob", "changed my mind")
        except Exception as exc:  # pragma: no cover - assertion below captures failures
            errors.append(exc)

    monkeypatch.setattr(ApprovalStore, "decisions", fake_decisions)

    first = threading.Thread(target=approve)
    second = threading.Thread(target=reject)
    first.start()
    if first_check_started.wait(timeout=1):
        second.start()
        release_first_writer.set()
    else:
        second.start()
    first.join(timeout=5)
    second.join(timeout=5)
    release_first_writer.set()

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(store.decisions("j1")) == 1
    assert sum(isinstance(exc, ApprovalError) for exc in errors) == 1


def test_reject_records_reason(data_root) -> None:
    store = ApprovalStore(data_root)

    record = store.reject("j1", "variant", "bob", "hat clips the ear")

    assert record.decision == "rejected"
    assert record.reason == "hat clips the ear"


def test_cannot_redecide_same_stage(data_root) -> None:
    store = ApprovalStore(data_root)
    store.approve("j1", "neutral", "alice")

    with pytest.raises(ApprovalError):
        store.reject("j1", "neutral", "alice", "changed my mind")


def test_decisions_are_persisted(data_root) -> None:
    ApprovalStore(data_root).approve("j1", "neutral", "alice")

    assert len(ApprovalStore(data_root).decisions("j1")) == 1


@pytest.mark.parametrize(
    ("job_id", "stage", "actor"),
    [
        (" ", "neutral", "alice"),
        ("j1", " ", "alice"),
        ("j1", "neutral", " "),
    ],
)
def test_approval_rejects_blank_identifiers(
    data_root,
    job_id: str,
    stage: str,
    actor: str,
) -> None:
    store = ApprovalStore(data_root)

    with pytest.raises(ValueError):
        store.approve(job_id, stage, actor)


def test_reject_requires_non_empty_reason(data_root) -> None:
    store = ApprovalStore(data_root)

    with pytest.raises(ValueError):
        store.reject("j1", "neutral", "alice", " \t ")
