from __future__ import annotations

from pathlib import Path

from fecreator.core.registry import SPEC_REGISTRY
from fecreator.specs.base import TargetSpec
from fecreator.specs.fire_emblem.gba.portrait_standard.spec import FeGbaPortraitStandard
from tests.fixtures.gba import write_valid_package


def test_id_and_protocol() -> None:
    spec = FeGbaPortraitStandard()
    assert spec.id == "fe-gba-portrait-standard"
    assert isinstance(spec, TargetSpec)


def test_registered_in_spec_registry() -> None:
    import fecreator.specs  # noqa: F401  (import triggers registration)

    assert "fe-gba-portrait-standard" in SPEC_REGISTRY.ids()


def test_validate_delegates(tmp_path: Path) -> None:
    write_valid_package(tmp_path)
    diags = FeGbaPortraitStandard().validate(tmp_path)
    assert all(d.severity.value != "error" for d in diags)
