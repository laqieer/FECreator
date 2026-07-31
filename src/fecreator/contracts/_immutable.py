from __future__ import annotations

from collections.abc import Mapping
from typing import NoReturn, TypeVar

T = TypeVar("T")


def _immutable(*args: object, **kwargs: object) -> NoReturn:
    raise TypeError("frozen mapping does not support mutation")


class FrozenDict(dict[str, T]):
    __delitem__ = _immutable
    __ior__ = _immutable
    __setitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __copy__(self) -> FrozenDict[T]:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> FrozenDict[T]:
        memo[id(self)] = self
        return self


def freeze_mapping(value: Mapping[str, T] | None = None) -> Mapping[str, T]:
    return FrozenDict(value or {})
