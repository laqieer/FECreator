from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from fecreator.core.paths import ensure_portable_filename, normalize_storage_id

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class DialogueBackgroundSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    id: str
    revision: str
    input_sha256: str

    @field_validator("kind", "id", "revision", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "source")

    @field_validator("input_sha256", mode="after")
    @classmethod
    def _validate_input_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("input_sha256 must be a lowercase SHA-256 hex digest")
        return value


class DialogueBackgroundPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0"] = "1.0"
    asset_type: Literal["dialogue_background"] = "dialogue_background"
    asset_type_version: Literal["1.0"] = "1.0"
    target_spec: Literal["fe8-dialogue-background-source-240x160"] = (
        "fe8-dialogue-background-source-240x160"
    )
    target_spec_version: Literal["1.0"] = "1.0"
    name: str
    purpose: str
    width: Literal[240] = 240
    height: Literal[160] = 160
    opaque: Literal[True] = True
    provider: str
    model: str | None = None
    prompt: str | None = None
    reference_pack: str | None = None
    reference_pack_rev: int | None = Field(default=None, ge=1)
    source: DialogueBackgroundSourceRecord
    png_sha256: str
    license_note: str
    source_note: str
    requested_downstream_profile: Literal["fe8-dialogue-background-feimg2"] | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = normalize_storage_id(value, field_name="name")
        return ensure_portable_filename(normalized, field_name="name")

    @field_validator("purpose", "provider", "license_note", "source_note", mode="after")
    @classmethod
    def _validate_text(cls, value: str, info: ValidationInfo) -> str:
        return _non_empty(value, field_name=info.field_name or "package metadata")

    @field_validator("png_sha256", mode="after")
    @classmethod
    def _validate_png_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("png_sha256 must be a lowercase SHA-256 hex digest")
        return value

    @model_validator(mode="after")
    def _reference_revision_matches(self) -> DialogueBackgroundPackageManifest:
        if (self.reference_pack is None) != (self.reference_pack_rev is None):
            raise ValueError("reference_pack and reference_pack_rev must be set together")
        return self
