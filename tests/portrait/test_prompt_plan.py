from fecreator.assets.portrait.prompt_plan import build_prompt_plan, plan_sources
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.references.model import ReferencePack


def _manifest(workflow: str = "text_to_portrait") -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow=workflow,
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight with red hair"),),
    )


def test_prompt_plan_includes_expressions():
    plan = build_prompt_plan(_manifest(), None)
    assert "brave knight" in plan.neutral_prompt
    assert "closed_eyes" in plan.expression_prompts


def test_plan_sources_contract():
    pack = ReferencePack(
        id="knight",
        revision=1,
        forbidden_changes=("hair color",),
        swatches=("#aa2222",),
    )
    plan = plan_sources(_manifest(), pack)
    assert "neutral.png" in plan.expected_filenames
    assert plan.background_contract.startswith("green")
    assert "hair color" in " ".join(plan.prompts) or "hair color" in str(plan.submission_schema)
    assert plan.required_expressions[0] == "neutral"
