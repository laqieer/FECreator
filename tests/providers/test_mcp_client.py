from __future__ import annotations

from pathlib import Path

import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.providers.base import GenRequest, ProviderRefusal
from fecreator.providers.mcp_client import McpClientProvider


class _FakeTransport:
    def call_tool(self, name: str, args: dict[str, object]) -> dict[str, object]:
        assert name == "generate_image"
        assert args["request"]["prompt"] == "x"
        workspace = Path(str(args["workspace"]))
        (workspace / "generated").mkdir(parents=True, exist_ok=True)
        output = workspace / "generated" / "n.png"
        output.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {
            "ok": True,
            "artifacts": [
                {
                    "role": "neutral",
                    "path": "generated/n.png",
                    "media_type": "image/png",
                }
            ],
        }


def test_generate_maps_tool_call(tmp_path) -> None:
    provider = McpClientProvider(
        transport=_FakeTransport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": {Capability.TEXT_TO_IMAGE}},
    )

    response = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)

    assert response.ok is True
    assert response.artifacts[0].role == "neutral"
    assert len(response.artifacts[0].sha256) == 64


def test_generate_refuses_unconfigured_workflow(tmp_path) -> None:
    provider = McpClientProvider(
        transport=_FakeTransport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={},
        workflow_capabilities={},
    )

    with pytest.raises(ProviderRefusal):
        provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)


def test_generate_refuses_missing_required_capability(tmp_path) -> None:
    provider = McpClientProvider(
        transport=_FakeTransport(),
        capabilities=CapabilitySet(capabilities=frozenset()),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": {Capability.TEXT_TO_IMAGE}},
    )

    with pytest.raises(ProviderRefusal):
        provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)


def test_generate_refuses_unconfigured_provider(tmp_path) -> None:
    provider = McpClientProvider(
        transport=None,
        capabilities=CapabilitySet(capabilities=frozenset()),
        tool_map={},
        workflow_capabilities={},
    )

    with pytest.raises(ProviderRefusal):
        provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)


def test_all_providers_registered() -> None:
    import fecreator.providers  # noqa: F401

    assert set(PROVIDER_REGISTRY.ids()) >= {"manual", "fake", "command", "mcp-client"}
