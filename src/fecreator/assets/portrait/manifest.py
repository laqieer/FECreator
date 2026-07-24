from __future__ import annotations

from fecreator.contracts.capabilities import Capability

GREEN_BG: tuple[int, int, int] = (0, 248, 0)

WORKFLOWS: frozenset[str] = frozenset(
    {
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    }
)

REQUIRED_CAPS: dict[str, set[Capability]] = {
    "text_to_portrait": {Capability.TEXT_TO_IMAGE},
    "concept_to_portrait": {Capability.IMAGE_TO_IMAGE},
    "expression_refine": {Capability.IMAGE_TO_IMAGE},
    "masked_variant": {Capability.MASKED_EDIT},
}

PREFERRED_CAPS: dict[str, set[Capability]] = {
    "text_to_portrait": {Capability.SEED_CONTROL},
    "concept_to_portrait": {Capability.MULTI_REFERENCE, Capability.STYLE_REFERENCE},
    "expression_refine": {Capability.SESSION_REFINEMENT},
    "masked_variant": {Capability.BACKGROUND_CONTROL},
}

REQUIRED_EXPRESSIONS: tuple[str, ...] = (
    "neutral",
    "half_closed_eyes",
    "closed_eyes",
    "mouth1",
    "mouth2",
    "mouth3",
)


def validate_workflow(workflow: str) -> None:
    if workflow not in WORKFLOWS:
        raise ValueError(f"unknown portrait workflow: {workflow!r}")


def required_capabilities(workflow: str) -> set[Capability]:
    validate_workflow(workflow)
    return set(REQUIRED_CAPS[workflow])


def preferred_capabilities(workflow: str) -> set[Capability]:
    validate_workflow(workflow)
    return set(PREFERRED_CAPS[workflow])
