"""Shared adapter mappings for failures every interface must report identically.

Interface adapters stay thin: they translate one domain failure into the
transport's own envelope. Lock contention and persisted-job corruption are the
cases where all four adapters must agree, so the codes and the messages live
here once instead of drifting across CLI, HTTP, MCP, and WebSocket handlers.
"""

from __future__ import annotations

from fecreator.contracts.diagnostics import Diagnostic, error
from fecreator.jobs.store import JobCorruptionError

STORE_LOCK_TIMEOUT_CODE = "STORE_LOCK_TIMEOUT"
_STORE_LOCK_TIMEOUT_MESSAGE = (
    "job store lock is held by another operation; retry the request shortly"
)

CORRUPT_JOB_CODE = "CORRUPT_JOB"
_CORRUPT_JOB_MESSAGE = (
    "persisted job state is corrupt; back up and remove data/jobs/<job-id> to recover"
)


def store_lock_timeout_diagnostic(where: str | None = None) -> Diagnostic:
    """Describe lock contention without echoing the raw lock path.

    ``LockTimeoutError`` names the absolute job and sidecar paths so operators
    can debug a stuck store. That text must never reach a client, so callers
    pass an interface-scoped ``where`` (route, command, or tool name) instead of
    the exception detail.
    """

    return error(STORE_LOCK_TIMEOUT_CODE, _STORE_LOCK_TIMEOUT_MESSAGE, where=where)


def corrupt_job_diagnostic(exc: JobCorruptionError, *, where: str | None = None) -> Diagnostic:
    """Name the corrupt job without echoing the absolute store path.

    ``JobCorruptionError`` carries the offending job id as structured metadata,
    which is exactly what an operator needs to find the directory to remove. The
    chained cause quotes absolute paths, so only that id is reported; ``where``
    is the interface-scoped fallback used when the store could not attribute the
    corruption to a single job.
    """

    return error(CORRUPT_JOB_CODE, _CORRUPT_JOB_MESSAGE, where=exc.job_id or where)
