from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fecreator.contracts._immutable import freeze_mapping
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
    character_ref_pack_rev: int | None = Field(default=None, ge=1)
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    params: Params = Field(default_factory=freeze_mapping)

    @field_validator("params", mode="after")
    @classmethod
    def _freeze_params(cls, value: Params) -> Params:
        return freeze_mapping(value)

    @model_validator(mode="after")
    def _validate_reference_revision(self) -> Manifest:
        if self.character_ref_pack_rev is not None and self.character_ref_pack is None:
            raise ValueError("character_ref_pack_rev requires character_ref_pack")
        return self

    @model_validator(mode="after")
    def _edit_requires_masked_variant(self) -> Manifest:
        if self.edit is not None and self.workflow != "masked_variant":
            message = (
                "edit may only be set when workflow='masked_variant', "
                f"got workflow={self.workflow!r}"
            )
            raise ValueError(message)
        return self

    def content_hash(self) -> str:
        return content_hash(self)
