from __future__ import annotations

import sys
import textwrap

import pytest

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.providers.base import GenRequest, ProviderRefusal
from fecreator.providers.command import CommandProvider

PYTHON = sys.executable
CAPABILITIES = CapabilitySet(capabilities=frozenset({Capability.TEXT_TO_IMAGE}))


def _write_script(path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def test_command_provider_runs_without_env_leak_and_hashes_artifacts(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "gen.py"
    _write_script(
        script,
        """
        import json
        import os
        import sys
        from pathlib import Path

        if os.environ.get("SECRET_TOKEN"):
            print("SECRET_TOKEN leaked", file=sys.stderr)
            raise SystemExit(9)

        payload = json.load(sys.stdin)
        assert payload["version"] == "fecreator-provider/v1"
        workspace = Path(payload["workspace"])
        (workspace / "generated").mkdir(parents=True, exist_ok=True)
        (workspace / "generated" / "n.png").write_bytes(b"\\x89PNG\\r\\n\\x1a\\n")
        print(json.dumps({
            "version": "fecreator-provider/v1",
            "ok": True,
            "model": "ext-1",
            "artifacts": [
                {"role": "neutral", "path": "generated/n.png", "media_type": "image/png"}
            ],
        }))
        """,
    )
    monkeypatch.setenv("SECRET_TOKEN", "top-secret")
    provider = CommandProvider(argv=[PYTHON, str(script)], capabilities=CAPABILITIES)

    response = provider.generate(GenRequest(workflow="text_to_portrait", prompt="x"), tmp_path)

    assert response.ok is True
    assert response.model == "ext-1"
    assert len(response.artifacts[0].sha256) == 64


def test_command_provider_reports_nonzero_exit_and_redacts_stderr(tmp_path) -> None:
    script = tmp_path / "fail.py"
    _write_script(
        script,
        """
        import sys

        print("token=sk-abc123", file=sys.stderr)
        raise SystemExit(7)
        """,
    )
    provider = CommandProvider(argv=[PYTHON, str(script)], capabilities=CAPABILITIES)

    response = provider.generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is False
    assert response.diagnostics[0].code == "PROVIDER_COMMAND_FAILED"
    assert "exit code 7" in response.diagnostics[0].message
    assert "***" in response.diagnostics[0].message
    assert "sk-abc123" not in response.diagnostics[0].message


def test_command_provider_reports_invalid_json(tmp_path) -> None:
    script = tmp_path / "bad.py"
    _write_script(
        script,
        """
        print("{not-json}")
        """,
    )
    provider = CommandProvider(argv=[PYTHON, str(script)], capabilities=CAPABILITIES)

    response = provider.generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is False
    assert response.diagnostics[0].code == "PROVIDER_INVALID_RESPONSE"


def test_command_provider_times_out(tmp_path) -> None:
    script = tmp_path / "sleep.py"
    _write_script(
        script,
        """
        import time

        time.sleep(0.25)
        print("{}")
        """,
    )
    provider = CommandProvider(
        argv=[PYTHON, str(script)],
        capabilities=CAPABILITIES,
        timeout=0.01,
    )

    response = provider.generate(GenRequest(workflow="text_to_portrait"), tmp_path)

    assert response.ok is False
    assert response.diagnostics[0].code == "PROVIDER_TIMEOUT"


def test_command_provider_refuses_unconfigured_provider(tmp_path) -> None:
    provider = CommandProvider(argv=[], capabilities=CAPABILITIES)

    with pytest.raises(ProviderRefusal):
        provider.generate(GenRequest(workflow="text_to_portrait"), tmp_path)
