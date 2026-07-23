from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

DiagData = dict[str, str | int | float | bool]


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Severity
    message: str
    where: str | None = None
    data: DiagData | None = None


def error(
    code: str,
    message: str,
    *,
    where: str | None = None,
    data: DiagData | None = None,
) -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.ERROR, message=message, where=where, data=data)


def warning(
    code: str,
    message: str,
    *,
    where: str | None = None,
    data: DiagData | None = None,
) -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.WARNING, message=message, where=where, data=data)


def has_errors(diags: Sequence[Diagnostic]) -> bool:
    return any(diagnostic.severity is Severity.ERROR for diagnostic in diags)
