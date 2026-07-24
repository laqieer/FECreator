"""Tests for shared SourcePlan / PromptPlan / SubmissionSchema contracts.

Covers extra='forbid', frozen Mapping fields, and typed SubmissionSchema.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.assets.base import PromptPlan, SourcePlan, SubmissionSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schema(**overrides: object) -> SubmissionSchema:
    base: dict[str, object] = {
        "forbidden_changes": (),
        "canonical_swatches": (),
        "traits": {},
        "provenance": "",
        "rights": "",
        "files": "one PNG per expected filename",
    }
    base.update(overrides)
    return SubmissionSchema(**base)


def _source_plan(**overrides: object) -> SourcePlan:
    base: dict[str, object] = {
        "prompts": ("hero",),
        "reference_roles": {},
        "expected_filenames": ("neutral.png",),
        "required_expressions": ("neutral",),
        "background_contract": "green",
        "forbidden_colors": (),
        "submission_schema": _schema(),
    }
    base.update(overrides)
    return SourcePlan(**base)


# ---------------------------------------------------------------------------
# SubmissionSchema typed submodel
# ---------------------------------------------------------------------------


def test_submission_schema_round_trips() -> None:
    schema = _schema(
        forbidden_changes=("hair color",),
        canonical_swatches=("#aa2222",),
        traits={"hair": "red"},
        provenance="approved-2026",
        rights="internal",
    )
    assert schema.forbidden_changes == ("hair color",)
    assert schema.canonical_swatches == ("#aa2222",)
    assert schema.traits["hair"] == "red"
    assert schema.provenance == "approved-2026"
    assert schema.rights == "internal"


def test_submission_schema_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SubmissionSchema(
            forbidden_changes=(),
            canonical_swatches=(),
            traits={},
            provenance="",
            rights="",
            files="ok",
            unknown_field="extra",  # type: ignore[call-arg]
        )


def test_submission_schema_traits_is_frozen() -> None:
    schema = _schema(traits={"hair": "red"})
    with pytest.raises(TypeError):
        schema.traits["new_key"] = "val"  # type: ignore[index]


def test_submission_schema_attribute_assignment_blocked() -> None:
    schema = _schema(provenance="p")
    with pytest.raises(ValidationError):
        schema.provenance = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SourcePlan — extra='forbid'
# ---------------------------------------------------------------------------


def test_source_plan_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SourcePlan(
            prompts=("hero",),
            reference_roles={},
            expected_filenames=("neutral.png",),
            required_expressions=("neutral",),
            background_contract="green",
            forbidden_colors=(),
            submission_schema=_schema(),
            not_a_field="oops",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# SourcePlan — reference_roles is a frozen Mapping
# ---------------------------------------------------------------------------


def test_source_plan_reference_roles_is_frozen() -> None:
    plan = _source_plan(reference_roles={"concept_0": "refs/a.png"})
    with pytest.raises(TypeError):
        plan.reference_roles["new_key"] = "bad"  # type: ignore[index]


def test_source_plan_reference_roles_accepts_dict_and_freezes() -> None:
    plan = _source_plan(reference_roles={"concept_0": "refs/a.png"})
    assert plan.reference_roles["concept_0"] == "refs/a.png"


# ---------------------------------------------------------------------------
# PromptPlan — extra='forbid'
# ---------------------------------------------------------------------------


def test_prompt_plan_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PromptPlan(
            neutral_prompt="x",
            expression_prompts={},
            bad_field="extra",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# PromptPlan — expression_prompts is a frozen Mapping
# ---------------------------------------------------------------------------


def test_prompt_plan_expression_prompts_is_frozen() -> None:
    plan = PromptPlan(
        neutral_prompt="hero",
        expression_prompts={"half_closed_eyes": "hero, half closed eyes frame"},
    )
    with pytest.raises(TypeError):
        plan.expression_prompts["new_key"] = "bad"  # type: ignore[index]


def test_prompt_plan_expression_prompts_accepts_dict_and_freezes() -> None:
    plan = PromptPlan(neutral_prompt="x", expression_prompts={"closed_eyes": "y"})
    assert plan.expression_prompts["closed_eyes"] == "y"
