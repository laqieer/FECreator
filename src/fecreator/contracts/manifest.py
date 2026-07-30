from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.lineage import Params, Region
from fecreator.core.hashing import content_hash
from fecreator.core.paths import ensure_portable_filename, normalize_storage_id

PORTRAIT_WORKFLOWS = frozenset(
    {"text_to_portrait", "concept_to_portrait", "expression_refine", "masked_variant"}
)
DIALOGUE_BACKGROUND_WORKFLOWS = frozenset(
    {"text_to_dialogue_background", "concept_to_dialogue_background", "masked_variant"}
)
APPROVED_BASE_WORKFLOWS = frozenset({"expression_refine", "masked_variant"})
"""Workflows that consume an already-approved portrait as their starting point."""


def _non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class SourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    id: str
    revision: str

    @field_validator("kind", "id", "revision", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "source identity")


class AssetMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    purpose: str
    source: SourceIdentity
    license_note: str
    source_note: str
    requested_downstream_profile: Literal["fe8-dialogue-background-feimg2"] | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = normalize_storage_id(value, field_name="name")
        return ensure_portable_filename(normalized, field_name="name")

    @field_validator("purpose", "license_note", "source_note", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "metadata")


class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["text", "concept_art", "approved_portrait", "approved_dialogue_background"]
    ref: str


class EditSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mask_path: str
    protected_regions: tuple[Region, ...] = ()


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    asset_type: Literal["portrait", "dialogue_background"]
    target_spec: Literal["fe-gba-portrait-standard", "fe8-dialogue-background-source-240x160"]
    workflow: Literal[
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
        "text_to_dialogue_background",
        "concept_to_dialogue_background",
    ]
    provider: str
    character_ref_pack: str | None = None
    character_ref_pack_rev: int | None = Field(default=None, ge=1)
    parent_asset_id: str | None = None
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    metadata: AssetMetadata | None = None
    params: Params = Field(default_factory=freeze_mapping)

    @field_validator("params", mode="after")
    @classmethod
    def _freeze_params(cls, value: Params) -> Params:
        return freeze_mapping(value)

    @field_validator("parent_asset_id", mode="after")
    @classmethod
    def _normalize_parent_asset_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("parent_asset_id must be a non-empty string when present")
        return normalized

    @model_validator(mode="after")
    def _validate_reference_revision(self) -> Manifest:
        if self.character_ref_pack_rev is not None and self.character_ref_pack is None:
            raise ValueError("character_ref_pack_rev requires character_ref_pack")
        return self

    @model_validator(mode="after")
    def _parent_asset_id_matches_workflow(self) -> Manifest:
        """Bind the approved base to the lineage graph, or refuse the manifest.

        ``expression_refine`` and ``masked_variant`` derive a new candidate from
        an approved portrait, so the resulting lineage node must name that base
        as a parent. The originating workflows have no approved input, so a
        parent there would record an edge that never happened.
        """

        consumes_approved_base = self.workflow in APPROVED_BASE_WORKFLOWS
        if consumes_approved_base and self.parent_asset_id is None:
            raise ValueError(
                f"parent_asset_id is required when workflow={self.workflow!r} "
                "so the approved base is recorded as a lineage parent"
            )
        if not consumes_approved_base and self.parent_asset_id is not None:
            raise ValueError(
                "parent_asset_id may only be set when workflow is one of "
                f"{sorted(APPROVED_BASE_WORKFLOWS)}, got workflow={self.workflow!r}"
            )
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

    @model_validator(mode="after")
    def _asset_contract_matches(self) -> Manifest:
        if self.asset_type == "portrait":
            if self.target_spec != "fe-gba-portrait-standard":
                raise ValueError("portrait requires target_spec='fe-gba-portrait-standard'")
            if self.workflow not in PORTRAIT_WORKFLOWS:
                raise ValueError(f"portrait does not support workflow={self.workflow!r}")
            if self.metadata is not None:
                raise ValueError("metadata is only supported for dialogue_background")
            return self

        if self.target_spec != "fe8-dialogue-background-source-240x160":
            raise ValueError(
                "dialogue_background requires target_spec='fe8-dialogue-background-source-240x160'"
            )
        if self.workflow not in DIALOGUE_BACKGROUND_WORKFLOWS:
            raise ValueError(f"dialogue_background does not support workflow={self.workflow!r}")
        if self.metadata is None:
            raise ValueError("metadata is required for dialogue_background")
        return self

    def content_hash(self) -> str:
        return content_hash(self)
