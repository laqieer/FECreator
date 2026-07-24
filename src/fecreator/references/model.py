from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.result import Artifact


def _ensure_non_empty_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _optional_non_empty_text(value: str) -> str:
    if not value:
        return value
    return _ensure_non_empty_text(value, field_name="text")


class ReferencePack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    revision: int = Field(ge=1)
    source: str = ""
    concept_art: tuple[Artifact, ...] = ()
    traits: Mapping[str, str] = Field(default_factory=freeze_mapping)
    swatches: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    provenance: str = ""
    rights: str = ""

    @field_validator("id", mode="after")
    @classmethod
    def _validate_id(cls, value: str, info: ValidationInfo) -> str:
        if value != value.strip():
            raise ValueError(
                f"{info.field_name or 'id'} must not have leading or trailing whitespace"
            )
        return _ensure_non_empty_text(value, field_name=info.field_name or "id")

    @field_validator("source", "provenance", "rights", mode="after")
    @classmethod
    def _validate_optional_text(cls, value: str) -> str:
        return _optional_non_empty_text(value)

    @field_validator("swatches", "forbidden_changes", mode="after")
    @classmethod
    def _validate_non_empty_entries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_ensure_non_empty_text(entry, field_name="entry") for entry in value)

    @field_validator("traits", mode="after")
    @classmethod
    def _freeze_traits(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        frozen = freeze_mapping(value)
        for key, item in frozen.items():
            _ensure_non_empty_text(key, field_name="trait key")
            _ensure_non_empty_text(item, field_name=f"trait[{key}]")
        return frozen
