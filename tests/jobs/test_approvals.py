from __future__ import annotations

import pytest

from fecreator.jobs.approvals import ApprovalError, ApprovalStore


def test_approve_and_read(data_root) -> None:
    store = ApprovalStore(data_root)

    record = store.approve("j1", "neutral", "alice")

    assert record.decision == "approved"
    assert record.actor == "alice"
    assert [decision.stage for decision in store.decisions("j1")] == ["neutral"]


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
