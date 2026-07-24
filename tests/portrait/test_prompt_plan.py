from fecreator.assets.portrait.prompt_plan import build_prompt_plan, plan_sources
from fecreator.contracts.manifest import Manifest, SourceSpec
from fecreator.contracts.result import Artifact
from fecreator.references.model import ReferencePack


def _manifest(workflow: str = "text_to_portrait") -> Manifest:
    return Manifest(
        asset_type="portrait",
        target_spec="fe-gba-portrait-standard",
        workflow=workflow,
        provider="fake",
        sources=(SourceSpec(kind="text", ref="a brave knight with red hair"),),
    )


def test_prompt_plan_includes_expressions() -> None:
    plan = build_prompt_plan(_manifest(), None)
    assert "brave knight" in plan.neutral_prompt
    assert "closed_eyes" in plan.expression_prompts


def test_plan_sources_contract() -> None:
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


# ---------------------------------------------------------------------------
# NEW: swatches must not be forbidden_colors (HIGH bug fix)
# ---------------------------------------------------------------------------


def test_swatches_not_mapped_to_forbidden_colors() -> None:
    """pack.swatches are canonical reference palette, NOT forbidden colors."""
    pack = ReferencePack(
        id="knight",
        revision=1,
        swatches=("#aa2222", "#4455aa"),
    )
    plan = plan_sources(_manifest(), pack)
    assert plan.forbidden_colors == ()


def test_canonical_swatches_in_submission_schema() -> None:
    """Canonical swatches surfaced as reference palette in submission metadata."""
    pack = ReferencePack(id="knight", revision=1, swatches=("#aa2222",))
    plan = plan_sources(_manifest(), pack)
    assert "#aa2222" in plan.submission_schema.canonical_swatches


# ---------------------------------------------------------------------------
# NEW: reference_roles must use artifact paths, delegate to references module
# ---------------------------------------------------------------------------


def test_reference_roles_use_artifact_paths() -> None:
    """reference_roles values are artifact paths, not role strings."""
    art = Artifact(
        role="concept", path="refs/hero.png", sha256="a" * 64, media_type="image/png"
    )
    pack = ReferencePack(id="knight", revision=1, concept_art=(art,))
    plan = plan_sources(_manifest("concept_to_portrait"), pack)
    assert "refs/hero.png" in plan.reference_roles.values()
    assert "concept" not in plan.reference_roles.values()  # role string must NOT be a value


def test_reference_roles_empty_when_no_concept_art() -> None:
    pack = ReferencePack(id="knight", revision=1)
    plan = plan_sources(_manifest(), pack)
    assert plan.reference_roles == {}


# ---------------------------------------------------------------------------
# NEW: provenance, rights, traits propagated into submission metadata
# ---------------------------------------------------------------------------


def test_provenance_and_rights_in_submission_schema() -> None:
    pack = ReferencePack(
        id="knight",
        revision=1,
        provenance="approved-2026-board",
        rights="internal-assets-only",
    )
    plan = plan_sources(_manifest(), pack)
    assert plan.submission_schema.provenance == "approved-2026-board"
    assert plan.submission_schema.rights == "internal-assets-only"


def test_traits_in_submission_schema() -> None:
    pack = ReferencePack(
        id="knight",
        revision=1,
        traits={"hair": "red", "eyes": "blue"},
    )
    plan = plan_sources(_manifest(), pack)
    assert plan.submission_schema.traits["hair"] == "red"
    assert plan.submission_schema.traits["eyes"] == "blue"


def test_plan_sources_null_pack_safe_defaults() -> None:
    """plan_sources with no pack produces safe empty defaults."""
    plan = plan_sources(_manifest(), None)
    assert plan.forbidden_colors == ()
    assert plan.reference_roles == {}
    assert plan.submission_schema.canonical_swatches == ()
    assert plan.submission_schema.provenance == ""
    assert plan.submission_schema.rights == ""
