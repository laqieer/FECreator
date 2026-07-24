from __future__ import annotations

from pathlib import Path

import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.providers.base import (
    GenRequest,
    GenResponse,
    Provider,
    ProviderRefusal,
    require_capabilities,
)


class _ProviderStub:
    id = "stub"
    capabilities = CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE}))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        del request, workspace
        return GenResponse(ok=True)


def test_provider_protocol_is_runtime_checkable() -> None:
    assert isinstance(_ProviderStub(), Provider)


def test_require_capabilities_allows_supported_capabilities() -> None:
    require_capabilities(_ProviderStub(), {Capability.TEXT_TO_IMAGE})


def test_require_capabilities_refuses_missing_capabilities() -> None:
    with pytest.raises(ProviderRefusal) as excinfo:
        require_capabilities(_ProviderStub(), {Capability.MASKED_EDIT})

    assert "masked_edit" in str(excinfo.value)


def test_gen_request_defaults() -> None:
    request = GenRequest(workflow="text_to_portrait", prompt="knight")

    assert request.references == ()
    assert request.seed is None
    assert request.params == {}
