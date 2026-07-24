from fecreator.assets.portrait.references import concept_art_artifacts, reference_roles
from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack


def _pack() -> ReferencePack:
    arts = (
        Artifact(role="concept", path="refs/a.png", sha256="0" * 64, media_type="image/png"),
        Artifact(role="concept", path="refs/b.png", sha256="1" * 64, media_type="image/png"),
    )
    return ReferencePack(id="knight", revision=1, concept_art=arts)


def test_reference_roles_enumerated():
    roles = reference_roles(_pack())
    assert roles == {"concept_0": "refs/a.png", "concept_1": "refs/b.png"}


def test_concept_art_artifacts_passthrough():
    assert len(concept_art_artifacts(_pack())) == 2


def test_empty_pack():
    assert reference_roles(ReferencePack(id="x", revision=1)) == {}
