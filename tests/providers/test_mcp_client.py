from __future__ import annotations

import base64
from collections.abc import Mapping
from pathlib import Path

import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.providers.base import GenRequest, ProviderRefusal
from fecreator.providers.mcp_client import McpClientProvider


class _FakeTransport:
    def call_tool(self, name: str, args: Mapping[str, object]) -> dict[str, object]:
        assert name == "generate_image"
        request = args["request"]
        assert isinstance(request, dict)
        assert request["prompt"] == "x"
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
    requirements = {Capability.TEXT_TO_IMAGE}
    provider = McpClientProvider(
        transport=_FakeTransport(),
        capabilities=CapabilitySet(capabilities=frozenset()),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": requirements},
    )
    requirements.clear()

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


def test_generate_rejects_artifact_path_escape_without_writing_outside_workspace(tmp_path) -> None:
    outside = tmp_path.parent / "escaped.bin"

    class _EscapingTransport:
        def call_tool(self, name: str, args: Mapping[str, object]) -> dict[str, object]:
            del name, args
            return {
                "ok": True,
                "artifacts": [
                    {
                        "role": "neutral",
                        "path": f"..\\{outside.name}",
                        "media_type": "application/octet-stream",
                        "data_base64": base64.b64encode(b"evil").decode("ascii"),
                    }
                ],
            }

    provider = McpClientProvider(
        transport=_EscapingTransport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": {Capability.TEXT_TO_IMAGE}},
    )

    response = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)

    assert response.ok is False
    assert response.artifacts == ()
    assert response.diagnostics[0].code == "MCP_INVALID_RESPONSE"
    assert outside.exists() is False


def test_generate_rejects_invalid_artifact_base64(tmp_path) -> None:
    class _InvalidBase64Transport:
        def call_tool(self, name: str, args: Mapping[str, object]) -> dict[str, object]:
            del name, args
            return {
                "ok": True,
                "artifacts": [
                    {
                        "role": "neutral",
                        "path": "generated/n.bin",
                        "media_type": "application/octet-stream",
                        "data_base64": "!!!",
                    }
                ],
            }

    provider = McpClientProvider(
        transport=_InvalidBase64Transport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": {Capability.TEXT_TO_IMAGE}},
    )

    response = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)

    assert response.ok is False
    assert response.diagnostics[0].code == "MCP_INVALID_RESPONSE"


def test_generate_rejects_invalid_artifact_schema(tmp_path) -> None:
    class _SchemaTransport:
        def call_tool(self, name: str, args: Mapping[str, object]) -> dict[str, object]:
            del name, args
            return {"ok": True, "artifacts": [{"path": "generated/n.png"}]}

    provider = McpClientProvider(
        transport=_SchemaTransport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": {Capability.TEXT_TO_IMAGE}},
    )

    response = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)

    assert response.ok is False
    assert response.diagnostics[0].code == "MCP_INVALID_RESPONSE"


def test_generate_returns_redacted_transport_errors(tmp_path) -> None:
    class _BrokenTransport:
        def call_tool(self, name: str, args: Mapping[str, object]) -> dict[str, object]:
            del name, args
            raise RuntimeError("token=sk-live-secret")

    provider = McpClientProvider(
        transport=_BrokenTransport(),
        capabilities=CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE})),
        tool_map={"text_to_portrait": "generate_image"},
        workflow_capabilities={"text_to_portrait": {Capability.TEXT_TO_IMAGE}},
    )

    response = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)

    assert response.ok is False
    assert response.diagnostics[0].code == "MCP_TRANSPORT_ERROR"
    assert "***" in response.diagnostics[0].message
    assert "sk-live-secret" not in response.diagnostics[0].message


def test_all_providers_registered() -> None:
    import fecreator.providers  # noqa: F401

    assert set(PROVIDER_REGISTRY.ids()) >= {"manual", "fake", "command", "mcp-client"}
