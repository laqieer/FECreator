from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import error
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.core.redaction import redact
from fecreator.providers.base import (
    GenRequest,
    GenResponse,
    ProviderRefusal,
    require_capabilities,
)


class McpTransport(Protocol):
    def call_tool(self, name: str, args: Mapping[str, object]) -> dict[str, object]: ...


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
        self._tool_map = dict(tool_map)
        self._workflow_capabilities = {
            workflow: frozenset(required)
            for workflow, required in (workflow_capabilities or {}).items()
        }

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
        require_capabilities(self, set(required))

        payload = {
            "workspace": str(workspace),
            "request": request.model_dump(mode="json"),
        }
        try:
            response_data = self._transport.call_tool(tool_name, payload)
        except Exception as exc:  # noqa: BLE001
            return GenResponse(
                ok=False,
                diagnostics=(
                    error("MCP_TRANSPORT_ERROR", f"{self.id} transport error: {redact(str(exc))}"),
                ),
            )

        if not isinstance(response_data, Mapping):
            return _invalid_response(self.id, "returned invalid response object")

        workspace_root = workspace.resolve()
        try:
            artifacts = tuple(
                self._artifact_from_mapping(workspace_root, index, artifact)
                for index, artifact in enumerate(_artifacts_from_response(response_data))
            )
        except _InvalidMcpResponseError as exc:
            return _invalid_response(self.id, str(exc))
        return GenResponse(
            ok=bool(response_data.get("ok")),
            artifacts=artifacts,
            model=_optional_string(response_data.get("model")) or self.id,
        )

    def _artifact_from_mapping(
        self,
        workspace: Path,
        index: int,
        artifact: Mapping[str, str],
    ) -> Artifact:
        raw_path = artifact.get("path", f"generated/artifact-{index}")
        artifact_path = _safe_artifact_path(workspace, raw_path)
        inline_data = artifact.get("data_base64")
        if inline_data is not None:
            try:
                decoded = base64.b64decode(inline_data, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise _InvalidMcpResponseError("returned invalid artifact payload") from exc
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(decoded)
        if not artifact_path.is_file():
            raise _InvalidMcpResponseError("returned invalid artifact path")

        return Artifact(
            role=artifact["role"],
            path=artifact_path.relative_to(workspace).as_posix(),
            sha256=sha256_file(artifact_path),
            media_type=artifact["media_type"],
        )


def _invalid_response(provider_id: str, message: str) -> GenResponse:
    return GenResponse(
        ok=False,
        diagnostics=(error("MCP_INVALID_RESPONSE", f"{provider_id} {redact(message)}"),),
    )


class _InvalidMcpResponseError(Exception):
    """Raised when the MCP client transport returns invalid artifact data."""


def _normalized_path_parts(path: str) -> Sequence[str]:
    return PurePosixPath(path.replace("\\", "/")).parts


def _safe_artifact_path(workspace: Path, raw_path: str) -> Path:
    try:
        return safe_join(workspace, *_normalized_path_parts(raw_path))
    except PathEscapeError as exc:
        raise _InvalidMcpResponseError("returned invalid artifact path") from exc


def _artifacts_from_response(data: Mapping[str, Any]) -> tuple[Mapping[str, str], ...]:
    raw_artifacts = data.get("artifacts", ())
    if raw_artifacts in (None, ()):
        return ()
    if not isinstance(raw_artifacts, list):
        raise _InvalidMcpResponseError("returned invalid artifact list")

    artifacts: list[Mapping[str, str]] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            raise _InvalidMcpResponseError("returned invalid artifact schema")
        if not (
            isinstance(artifact.get("role"), str) and isinstance(artifact.get("media_type"), str)
        ):
            raise _InvalidMcpResponseError("returned invalid artifact schema")

        raw_path = artifact.get("path")
        inline_data = artifact.get("data_base64")
        if not isinstance(raw_path, str):
            raise _InvalidMcpResponseError("returned invalid artifact path")
        if inline_data is not None and not isinstance(inline_data, str):
            raise _InvalidMcpResponseError("returned invalid artifact payload")
        artifacts.append(artifact)
    return tuple(artifacts)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
