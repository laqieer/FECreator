from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fecreator.contracts.capabilities import CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic, error, warning
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
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
        try:
            proc = subprocess.run(
                self._argv,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
                env=_safe_subprocess_env(),
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

        stderr_text = _bounded_redacted_text(proc.stderr, self._max_output_chars)
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
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return GenResponse(
                ok=False,
                diagnostics=(
                    error(
                        "PROVIDER_INVALID_RESPONSE",
                        (
                            f"provider {self.id} returned invalid JSON"
                            f"{_diagnostic_suffix(proc.stdout, self._max_output_chars)}"
                        ),
                    ),
                ),
            )

        if data.get("version") != PROTOCOL_VERSION:
            return GenResponse(
                ok=False,
                diagnostics=(
                    error(
                        "PROVIDER_INVALID_RESPONSE",
                        (
                            f"provider {self.id} returned unsupported protocol version"
                            f" {data.get('version')!r}"
                        ),
                    ),
                ),
            )

        diagnostics: tuple[Diagnostic, ...] = ()
        if stderr_text:
            diagnostics = (warning("PROVIDER_STDERR", stderr_text),)

        artifacts = tuple(
            _artifact_from_mapping(workspace, artifact)
            for artifact in _artifacts_from_response(data)
        )
        return GenResponse(
            ok=bool(data.get("ok")),
            artifacts=artifacts,
            model=_optional_string(data.get("model")),
            diagnostics=diagnostics,
        )


def _safe_subprocess_env() -> dict[str, str]:
    env = {"PYTHONIOENCODING": "utf-8"}
    for key in ("SYSTEMROOT", "WINDIR", "COMSPEC"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _bounded_redacted_text(text: str | None, limit: int) -> str:
    if not text:
        return ""

    redacted = redact(text.strip())
    if len(redacted) <= limit:
        return redacted
    return f"{redacted[:limit]}... [truncated]"


def _diagnostic_suffix(text: str | None, limit: int = 4096) -> str:
    bounded = _bounded_redacted_text(text, limit)
    return f": {bounded}" if bounded else ""


def _artifacts_from_response(data: Mapping[str, Any]) -> tuple[Mapping[str, str], ...]:
    raw_artifacts = data.get("artifacts", ())
    if not isinstance(raw_artifacts, list):
        return ()

    artifacts: list[Mapping[str, str]] = []
    for artifact in raw_artifacts:
        if (
            isinstance(artifact, Mapping)
            and isinstance(artifact.get("role"), str)
            and isinstance(artifact.get("path"), str)
            and isinstance(artifact.get("media_type"), str)
        ):
            artifacts.append(artifact)
    return tuple(artifacts)


def _artifact_from_mapping(workspace: Path, artifact: Mapping[str, str]) -> Artifact:
    artifact_path = workspace / artifact["path"]
    return Artifact(
        role=artifact["role"],
        path=artifact["path"],
        sha256=sha256_file(artifact_path),
        media_type=artifact["media_type"],
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _coerce_text(value: str | bytes | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")
