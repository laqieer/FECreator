from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.imaging.io import save_png
from fecreator.providers.base import GenRequest, GenResponse


class FakeProvider:
    id = "fake"
    capabilities = CapabilitySet(capabilities=frozenset(Capability))

    def generate(self, request: GenRequest, workspace: Path) -> GenResponse:
        digest = hashlib.sha256((request.prompt or "").encode("utf-8")).digest()
        width = int(request.params.get("width", 96))
        height = int(request.params.get("height", 80))
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        rgb[:, :] = (digest[0], digest[1], digest[2])

        output = workspace / "generated" / "neutral.png"
        save_png(output, rgb)

        artifact = Artifact(
            role="neutral",
            path="generated/neutral.png",
            sha256=sha256_file(output),
            media_type="image/png",
        )
        return GenResponse(ok=True, artifacts=(artifact,), model="fake-1", seed=request.seed or 0)
