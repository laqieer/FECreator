from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Capability(StrEnum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    MULTI_REFERENCE = "multi_reference"
    MASKED_EDIT = "masked_edit"
    SESSION_REFINEMENT = "session_refinement"
    POSE_CONTROL = "pose_control"
    LINEART_CONTROL = "lineart_control"
    IDENTITY_EMBEDDING = "identity_embedding"
    STYLE_REFERENCE = "style_reference"
    SEED_CONTROL = "seed_control"
    SIZE_CONTROL = "size_control"
    BACKGROUND_CONTROL = "background_control"
    ASYNCHRONOUS_JOBS = "asynchronous_jobs"


class CapabilitySet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capabilities: frozenset[Capability]

    def supports(self, required: set[Capability]) -> bool:
        return required.issubset(self.capabilities)

    def missing(self, required: set[Capability]) -> set[Capability]:
        return set(required) - set(self.capabilities)
