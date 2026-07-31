from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import error
from fecreator.contracts.result import Artifact
from fecreator.core.hashing import sha256_file
from fecreator.providers.base import GenRequest, GenResponse

_SUPPORTED_IMAGE_FORMATS = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


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
        if not submitted.exists():
            return GenResponse(ok=False)

        artifacts: list[Artifact] = []
        for file_path in sorted(submitted.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.name.endswith((".manifest.json", ".pal")):
                continue
            media_type = _detect_media_type(file_path)
            if media_type is None:
                return GenResponse(
                    ok=False,
                    diagnostics=(
                        error(
                            "MANUAL_UNSUPPORTED_SUBMISSION",
                            "manual provider requires supported image files",
                        ),
                    ),
                )
            artifacts.append(
                Artifact(
                    role=file_path.stem,
                    path=f"submitted/{file_path.name}",
                    sha256=sha256_file(file_path),
                    media_type=media_type,
                )
            )
        return GenResponse(ok=bool(artifacts), artifacts=tuple(artifacts))


def _detect_media_type(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            image.load()
            image_format = image.format
    except (OSError, UnidentifiedImageError):
        return None
    if image_format is None:
        return None
    return _SUPPORTED_IMAGE_FORMATS.get(image_format.upper())
