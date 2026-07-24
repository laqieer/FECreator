from __future__ import annotations

from pathlib import Path

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.providers.base import GenRequest, GenResponse


class ManualProvider:
    id = "manual"
    capabilities = CapabilitySet(
        capabilities=frozenset(
            {
                Capability.TEXT_TO_IMAGE,
                Capability.IMAGE_TO_IMAGE,
                Capability.MULTI_REFERENCE,
                Capability.MASKED_EDIT,
            }
        )
    )

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        del request
        submitted = workspace / "submitted"
        artifacts = (
            tuple(
                Artifact(
                    role=file_path.stem,
                    path=f"submitted/{file_path.name}",
                    sha256=sha256_file(file_path),
                    media_type="image/png",
                )
                for file_path in sorted(submitted.iterdir())
                if file_path.is_file()
            )
            if submitted.exists()
            else ()
        )
        return GenResponse(ok=bool(artifacts), artifacts=artifacts)
