from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class UnknownIdError(KeyError):
    """Raised when a registry id is not registered."""


class Registry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(self, id: str, value: T) -> None:
        if id in self._items:
            raise ValueError(f"id already registered: {id}")
        self._items[id] = value

    def get(self, id: str) -> T:
        try:
            return self._items[id]
        except KeyError as exc:
            raise UnknownIdError(id) from exc

    def ids(self) -> list[str]:
        return list(self._items)


ASSET_REGISTRY: Registry[object] = Registry()
SPEC_REGISTRY: Registry[object] = Registry()
PROVIDER_REGISTRY: Registry[object] = Registry()
