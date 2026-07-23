from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fecreator.contracts.lineage import Params, Region
from fecreator.core.hashing import content_hash


class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["text", "concept_art", "approved_portrait"]
    ref: str


class EditSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mask_path: str
    protected_regions: tuple[Region, ...] = ()


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    asset_type: Literal["portrait"]
    target_spec: Literal["fe-gba-portrait-standard"]
    workflow: Literal[
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    ]
    provider: str
    character_ref_pack: str | None = None
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    params: Params = Field(default_factory=dict)

    def content_hash(self) -> str:
        return content_hash(self)
