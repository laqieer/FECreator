from __future__ import annotations

import base64
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.providers.base import (
    GenRequest,
    GenResponse,
    ProviderRefusal,
    require_capabilities,
)


class McpTransport(Protocol):
    def call_tool(self, name: str, args: dict[str, object]) -> dict[str, object]: ...


class McpClientProvider:
    def __init__(
        self,
        transport: McpTransport | None,
        capabilities: CapabilitySet,
        tool_map: dict[str, str],
        *,
        workflow_capabilities: Mapping[str, set[Capability]] | None = None,
        id: str = "mcp-client",
    ) -> None:
        self.id = id
        self.capabilities = capabilities
        self._transport = transport
        self._tool_map = tool_map
        self._workflow_capabilities = dict(workflow_capabilities or {})

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        if self._transport is None:
            raise ProviderRefusal(f"{self.id} is not configured")

        tool_name = self._tool_map.get(request.workflow)
        if tool_name is None:
            raise ProviderRefusal(f"{self.id} workflow {request.workflow!r} is not configured")

        required = self._workflow_capabilities.get(request.workflow)
        if required is None:
            raise ProviderRefusal(
                f"{self.id} workflow {request.workflow!r} has no capability mapping"
            )
        require_capabilities(self, required)

        payload = {
            "workspace": str(workspace),
            "request": request.model_dump(mode="json"),
        }
        data = self._transport.call_tool(tool_name, payload)
        artifacts = tuple(
            self._artifact_from_mapping(workspace, index, artifact)
            for index, artifact in enumerate(_artifacts_from_response(data))
        )
        return GenResponse(
            ok=bool(data.get("ok")),
            artifacts=artifacts,
            model=_optional_string(data.get("model")) or self.id,
        )

    def _artifact_from_mapping(
        self,
        workspace: Path,
        index: int,
        artifact: Mapping[str, str],
    ) -> Artifact:
        artifact_path = workspace / artifact.get("path", f"generated/artifact-{index}")
        inline_data = artifact.get("data_base64")
        if inline_data is not None:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(base64.b64decode(inline_data))

        return Artifact(
            role=artifact["role"],
            path=str(artifact_path.relative_to(workspace)),
            sha256=sha256_file(artifact_path),
            media_type=artifact["media_type"],
        )


def _artifacts_from_response(data: Mapping[str, Any]) -> tuple[Mapping[str, str], ...]:
    raw_artifacts = data.get("artifacts", ())
    if not isinstance(raw_artifacts, list):
        return ()

    artifacts: list[Mapping[str, str]] = []
    for artifact in raw_artifacts:
        if (
            isinstance(artifact, Mapping)
            and isinstance(artifact.get("role"), str)
            and isinstance(artifact.get("media_type"), str)
        ):
            path = artifact.get("path")
            inline_data = artifact.get("data_base64")
            if isinstance(path, str) or isinstance(inline_data, str):
                artifacts.append(artifact)
    return tuple(artifacts)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
