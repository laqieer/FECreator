from __future__ import annotations

import pytest

from fecreator.core.registry import Registry, UnknownIdError


def test_register_get_ids() -> None:
    registry: Registry[int] = Registry()

    registry.register("a", 1)
    registry.register("b", 2)

    assert registry.get("a") == 1
    assert sorted(registry.ids()) == ["a", "b"]


def test_unknown_id_raises() -> None:
    registry: Registry[int] = Registry()

    with pytest.raises(UnknownIdError):
        registry.get("missing")


def test_duplicate_registration_raises() -> None:
    registry: Registry[int] = Registry()
    registry.register("a", 1)

    with pytest.raises(ValueError):
        registry.register("a", 2)
