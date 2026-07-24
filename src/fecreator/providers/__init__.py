from __future__ import annotations

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.providers.command import CommandProvider
from fecreator.providers.fake import FakeProvider
from fecreator.providers.manual import ManualProvider
from fecreator.providers.mcp_client import McpClientProvider

_EMPTY_CAPABILITIES = CapabilitySet(capabilities=frozenset())


def _register(provider_id: str, provider: object) -> None:
    if provider_id not in set(PROVIDER_REGISTRY.ids()):
        PROVIDER_REGISTRY.register(provider_id, provider)


_register("manual", ManualProvider())
_register("fake", FakeProvider())
_register("command", CommandProvider(argv=[], capabilities=_EMPTY_CAPABILITIES))
_register(
    "mcp-client",
    McpClientProvider(
        transport=None,
        capabilities=_EMPTY_CAPABILITIES,
        tool_map={},
        workflow_capabilities={},
    ),
)
