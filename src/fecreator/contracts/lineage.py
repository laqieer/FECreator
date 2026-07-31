from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from fecreator.contracts._immutable import freeze_mapping

Params = Mapping[str, str | int | float | bool]
_AWARE_DATETIME = TypeAdapter(AwareDatetime)


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    label: str


class Operation(StrEnum):
    IMPORT_CONCEPT = "import_concept"
    CREATE_NEUTRAL = "create_neutral"
    CREATE_DIALOGUE_BACKGROUND = "create_dialogue_background"
    IMPORT_DIALOGUE_BACKGROUND_CONCEPT = "import_dialogue_background_concept"
    REFINE_EXPRESSION = "refine_expression"
    VARIANT_MASKED_EDIT = "variant_masked_edit"
    EXPORT_SPEC = "export_spec"


class LineageNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str
    operation: Operation
    parents: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None
    reference_pack: str | None = None
    reference_pack_rev: int | None = None
    seed: int | None = None
    params: Params = Field(default_factory=freeze_mapping)
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: Mapping[str, float] = Field(default_factory=freeze_mapping)
    approved_by: str | None = None
    output_hashes: tuple[str, ...] = ()
    created_at: str = Field(json_schema_extra={"format": "date-time"})

    @field_validator("params", "metrics", mode="after")
    @classmethod
    def _freeze_mapping_fields(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_mapping(value)

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: str) -> str:
        _AWARE_DATETIME.validate_python(value)
        return value
