"""Shared adapter mappings for failures every interface must report identically.

Interface adapters stay thin: they translate one domain failure into the
transport's own envelope. Lock contention is the case where all four adapters
must agree, so the code and the message live here once instead of drifting
across CLI, HTTP, MCP, and WebSocket handlers.
"""

from __future__ import annotations

from fecreator.contracts.diagnostics import Diagnostic, error

STORE_LOCK_TIMEOUT_CODE = "STORE_LOCK_TIMEOUT"
_STORE_LOCK_TIMEOUT_MESSAGE = (
    "job store lock is held by another operation; retry the request shortly"
)


def store_lock_timeout_diagnostic(where: str | None = None) -> Diagnostic:
    """Describe lock contention without echoing the raw lock path.

    ``LockTimeoutError`` names the absolute job and sidecar paths so operators
    can debug a stuck store. That text must never reach a client, so callers
    pass an interface-scoped ``where`` (route, command, or tool name) instead of
    the exception detail.
    """

    return error(STORE_LOCK_TIMEOUT_CODE, _STORE_LOCK_TIMEOUT_MESSAGE, where=where)
