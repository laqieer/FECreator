import pytest

from fecreator.assets.portrait.manifest import (
    GREEN_BG,
    WORKFLOWS,
    preferred_capabilities,
    required_capabilities,
    validate_workflow,
)
from fecreator.contracts.capabilities import Capability


def test_workflows():
    assert (
        frozenset(
            {"text_to_portrait", "concept_to_portrait", "expression_refine", "masked_variant"}
        )
        == WORKFLOWS
    )


def test_required_caps_per_workflow():
    assert required_capabilities("text_to_portrait") == {Capability.TEXT_TO_IMAGE}
    assert required_capabilities("masked_variant") == {Capability.MASKED_EDIT}
    assert required_capabilities("concept_to_portrait") == {Capability.IMAGE_TO_IMAGE}


def test_preferred_caps_for_concept():
    assert Capability.MULTI_REFERENCE in preferred_capabilities("concept_to_portrait")


def test_green_bg_is_gba_snapped():
    assert GREEN_BG == (0, 248, 0)


def test_validate_workflow_rejects_unknown():
    with pytest.raises(ValueError):
        validate_workflow("battle_sprite")
