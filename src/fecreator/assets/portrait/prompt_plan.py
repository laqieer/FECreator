from __future__ import annotations

from fecreator.assets.base import PromptPlan, SourcePlan
from fecreator.assets.portrait.manifest import REQUIRED_EXPRESSIONS
from fecreator.contracts.manifest import Manifest
from fecreator.references.model import ReferencePack


def _text(manifest: Manifest) -> str:
    return " ".join(s.ref for s in manifest.sources if s.kind == "text")


def build_prompt_plan(manifest: Manifest, pack: ReferencePack | None) -> PromptPlan:
    base = _text(manifest) or "a Fire Emblem GBA character portrait"
    forbidden = (
        f" (do not change: {', '.join(pack.forbidden_changes)})"
        if pack and pack.forbidden_changes
        else ""
    )
    neutral = f"{base}{forbidden}, neutral expression, front-facing bust"
    expressions = {
        name: f"{base}{forbidden}, {name.replace('_', ' ')} frame"
        for name in REQUIRED_EXPRESSIONS
        if name != "neutral"
    }
    return PromptPlan(neutral_prompt=neutral, expression_prompts=expressions)


def plan_sources(manifest: Manifest, pack: ReferencePack | None) -> SourcePlan:
    plan = build_prompt_plan(manifest, pack)
    prompts = (plan.neutral_prompt, *plan.expression_prompts.values())
    roles = (
        {f"concept_{i}": art.role for i, art in enumerate(pack.concept_art)}
        if pack
        else {}
    )
    forbidden_colors = pack.swatches if pack else ()
    return SourcePlan(
        prompts=prompts,
        reference_roles=roles,
        expected_filenames=(
            "neutral.png",
            *(f"{n}.png" for n in REQUIRED_EXPRESSIONS if n != "neutral"),
        ),
        required_expressions=REQUIRED_EXPRESSIONS,
        background_contract="green background at palette index 0, GBA 5-bit snapped",
        forbidden_colors=forbidden_colors,
        submission_schema={
            "forbidden_changes": list(pack.forbidden_changes) if pack else [],
            "files": "one indexed or RGB PNG per expected filename",
        },
    )
