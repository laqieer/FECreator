from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fecreator.contracts._immutable import freeze_mapping
from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic
from fecreator.contracts.lineage import Region
from fecreator.contracts.result import Artifact

Params = Mapping[str, str | int | float | bool]


class GenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow: str
    prompt: str | None = None
    references: tuple[Artifact, ...] = ()
    mask: Artifact | None = None
    protected_regions: tuple[Region, ...] = ()
    seed: int | None = None
    params: Params = Field(default_factory=freeze_mapping)

    @field_validator("params", mode="after")
    @classmethod
    def _freeze_params(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_mapping(value)


class GenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    artifacts: tuple[Artifact, ...] = ()
    model: str | None = None
    seed: int | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


class ProviderRefusal(Exception):
    """Raised when a provider refuses a request."""


@runtime_checkable
class Provider(Protocol):
    id: str
    capabilities: CapabilitySet

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse: ...


def require_capabilities(provider: Provider, required: set[Capability]) -> None:
    missing = provider.capabilities.missing(required)
    if not missing:
        return

    names = ", ".join(sorted(capability.value for capability in missing))
    raise ProviderRefusal(f"provider {provider.id} missing capabilities: {names}")
