from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.capabilities import Capability, CapabilitySet


def test_thirteen_capabilities() -> None:
    assert len(list(Capability)) == 13
    assert Capability.MASKED_EDIT.value == "masked_edit"


def test_supports_and_missing() -> None:
    capability_set = CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE}))

    assert capability_set.supports({Capability.TEXT_TO_IMAGE}) is True
    assert capability_set.supports({Capability.MASKED_EDIT}) is False
    assert capability_set.missing({Capability.TEXT_TO_IMAGE, Capability.MASKED_EDIT}) == {
        Capability.MASKED_EDIT
    }


def test_frozen() -> None:
    capability_set = CapabilitySet(capabilities=frozenset())

    with pytest.raises((ValidationError, TypeError)):
        capability_set.capabilities = frozenset({Capability.SEED_CONTROL})


def test_capability_set_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CapabilitySet(capabilities=frozenset(), unexpected="value")
