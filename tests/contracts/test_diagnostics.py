from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.diagnostics import Diagnostic, Severity, error, has_errors, warning


def test_error_helper_sets_severity() -> None:
    diagnostic = error("BAD", "boom", where="file.png")

    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.code == "BAD"
    assert diagnostic.where == "file.png"


def test_has_errors() -> None:
    diagnostics = [warning("W", "warn"), error("E", "explode")]

    assert has_errors(diagnostics) is True
    assert has_errors([warning("W", "warn")]) is False


def test_diagnostic_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Diagnostic(code="BAD", severity=Severity.ERROR, message="boom", unexpected="value")
