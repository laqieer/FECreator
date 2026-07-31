from __future__ import annotations

from fecreator.contracts.capabilities import Capability

WORKFLOWS = frozenset(
    {"text_to_dialogue_background", "concept_to_dialogue_background", "masked_variant"}
)

REQUIRED_CAPS = {
    "text_to_dialogue_background": {Capability.TEXT_TO_IMAGE},
    "concept_to_dialogue_background": {Capability.IMAGE_TO_IMAGE},
    "masked_variant": {Capability.MASKED_EDIT},
}

PREFERRED_CAPS = {
    "text_to_dialogue_background": {Capability.SEED_CONTROL, Capability.SIZE_CONTROL},
    "concept_to_dialogue_background": {
        Capability.MULTI_REFERENCE,
        Capability.STYLE_REFERENCE,
        Capability.SIZE_CONTROL,
    },
    "masked_variant": {Capability.BACKGROUND_CONTROL, Capability.SIZE_CONTROL},
}


def _validate_workflow(workflow: str) -> None:
    if workflow not in WORKFLOWS:
        raise ValueError(f"unknown dialogue background workflow: {workflow!r}")


def required_capabilities(workflow: str) -> set[Capability]:
    _validate_workflow(workflow)
    return set(REQUIRED_CAPS[workflow])


def preferred_capabilities(workflow: str) -> set[Capability]:
    _validate_workflow(workflow)
    return set(PREFERRED_CAPS[workflow])
