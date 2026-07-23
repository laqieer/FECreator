from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

Params = dict[str, str | int | float | bool]


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: int
    y: int
    w: int
    h: int
    label: str


class Operation(str, Enum):
    IMPORT_CONCEPT = "import_concept"
    CREATE_NEUTRAL = "create_neutral"
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
    params: Params = Field(default_factory=dict)
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: dict[str, float] = Field(default_factory=dict)
    approved_by: str | None = None
    output_hashes: tuple[str, ...] = ()
    created_at: str
