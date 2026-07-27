from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic, error, warning
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.core.paths import PathEscapeError, safe_join
from fecreator.core.process import bounded_redacted_text, safe_subprocess_env
from fecreator.core.redaction import redact
from fecreator.providers.base import GenRequest, GenResponse, ProviderRefusal

PROTOCOL_VERSION = "fecreator-provider/v1"


class CommandProvider:
    def __init__(
        self,
        argv: list[str],
        capabilities: CapabilitySet,
        *,
        id: str = "command",
        timeout: float = 120.0,
        max_output_chars: int = 4096,
    ) -> None:
        self.id = id
        self.capabilities = capabilities
        self._argv = argv
        self._timeout = timeout
        self._max_output_chars = max_output_chars

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        if not self._argv:
            raise ProviderRefusal(f"{self.id} is not configured")

        payload = {
            "version": PROTOCOL_VERSION,
            "workspace": str(workspace),
            "request": request.model_dump(mode="json"),
        }
        workspace_root = workspace.resolve()
        try:
            proc = subprocess.run(
                self._argv,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
                env=safe_subprocess_env(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return GenResponse(
                ok=False,
                diagnostics=(
                    error(
                        "PROVIDER_TIMEOUT",
                        (
                            f"provider {self.id} timed out after {self._timeout:.3f}s"
                            f"{_diagnostic_suffix(_coerce_text(exc.stderr))}"
                        ),
                    ),
                ),
            )

        stderr_text = bounded_redacted_text(proc.stderr, self._max_output_chars)
        if proc.returncode != 0:
            return GenResponse(
                ok=False,
                diagnostics=(
                    error(
                        "PROVIDER_COMMAND_FAILED",
                        (
                            f"provider {self.id} failed with exit code {proc.returncode}"
                            f"{_diagnostic_suffix(stderr_text)}"
                        ),
                    ),
                ),
            )

        try:
            decoded = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return _invalid_response(
                self.id,
                f"returned invalid JSON{_diagnostic_suffix(proc.stdout, self._max_output_chars)}",
            )

        if not isinstance(decoded, Mapping):
            return _invalid_response(self.id, "returned non-object JSON")
        if decoded.get("version") != PROTOCOL_VERSION:
            return _invalid_response(
                self.id, f"returned unsupported protocol version {decoded.get('version')!r}"
            )

        diagnostics: tuple[Diagnostic, ...] = ()
        if stderr_text:
            diagnostics = (warning("PROVIDER_STDERR", stderr_text),)

        try:
            artifacts = tuple(
                _artifact_from_mapping(workspace_root, artifact)
                for artifact in _artifacts_from_response(decoded)
            )
        except _InvalidProviderResponseError as exc:
            return _invalid_response(self.id, str(exc))
        return GenResponse(
            ok=bool(decoded.get("ok")),
            artifacts=artifacts,
            model=_optional_string(decoded.get("model")),
            diagnostics=diagnostics,
        )


def _invalid_response(provider_id: str, message: str) -> GenResponse:
    return GenResponse(
        ok=False,
        diagnostics=(
            error("PROVIDER_INVALID_RESPONSE", f"provider {provider_id} {redact(message)}"),
        ),
    )


class _InvalidProviderResponseError(Exception):
    """Raised when an external command returns invalid response data."""


def _normalized_path_parts(path: str) -> Sequence[str]:
    return PurePosixPath(path.replace("\\", "/")).parts


def _safe_artifact_path(workspace: Path, raw_path: str) -> Path:
    try:
        return safe_join(workspace, *_normalized_path_parts(raw_path))
    except PathEscapeError as exc:
        raise _InvalidProviderResponseError("returned invalid artifact path") from exc


def _artifacts_from_response(data: Mapping[str, Any]) -> tuple[Mapping[str, str], ...]:
    raw_artifacts = data.get("artifacts", ())
    if raw_artifacts in (None, ()):
        return ()
    if not isinstance(raw_artifacts, list):
        raise _InvalidProviderResponseError("returned invalid artifact list")

    artifacts: list[Mapping[str, str]] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            raise _InvalidProviderResponseError("returned invalid artifact schema")
        if not (
            isinstance(artifact.get("role"), str)
            and isinstance(artifact.get("path"), str)
            and isinstance(artifact.get("media_type"), str)
        ):
            raise _InvalidProviderResponseError("returned invalid artifact schema")
        artifacts.append(artifact)
    return tuple(artifacts)


def _artifact_from_mapping(workspace: Path, artifact: Mapping[str, str]) -> Artifact:
    artifact_path = _safe_artifact_path(workspace, artifact["path"])
    if not artifact_path.is_file():
        raise _InvalidProviderResponseError("returned invalid artifact path")

    return Artifact(
        role=artifact["role"],
        path=artifact_path.relative_to(workspace).as_posix(),
        sha256=sha256_file(artifact_path),
        media_type=artifact["media_type"],
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _coerce_text(value: str | bytes | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _diagnostic_suffix(text: str | None, limit: int = 4096) -> str:
    bounded = bounded_redacted_text(text, limit)
    return f": {bounded}" if bounded else ""
