from __future__ import annotations

from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack


def reference_roles(pack: ReferencePack) -> dict[str, str]:
    return {f"concept_{i}": art.path for i, art in enumerate(pack.concept_art)}


def concept_art_artifacts(pack: ReferencePack) -> tuple[Artifact, ...]:
    return pack.concept_art
