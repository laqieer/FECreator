from __future__ import annotations

import re
from pathlib import Path

import yaml

from fecreator.assets.portrait.manifest import WORKFLOWS
from fecreator.interfaces.cli_json import build_parser
from fecreator.interfaces.mcp_server import TOOL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "fecreator"
SKILL = SKILL_DIR / "SKILL.md"
CAPABILITY_GAPS = SKILL_DIR / "references" / "capability-gaps.md"
PORTRAIT_NEUTRAL = SKILL_DIR / "agents" / "portrait-neutral.md"
INTERFACES_DOC = REPO_ROOT / "docs" / "interfaces.md"
SKILL_FILES = (SKILL, CAPABILITY_GAPS, PORTRAIT_NEUTRAL)
PLACEHOLDER_VALUES = {
    "JOB_ID": "job-123",
    "MANIFEST_PATH": "manifest.json",
    "PACKAGE_DIR": ".",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    return " ".join(_read(path).split())


def _frontmatter(path: Path) -> tuple[dict[str, object], str]:
    text = _read(path)
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None, f"missing frontmatter in {path}"
    payload = yaml.safe_load(match.group(1))
    assert isinstance(payload, dict), "frontmatter must be a mapping"
    return payload, text


def _cli_examples(text: str) -> list[str]:
    return re.findall(r"`(fecreator [^`\n]+)`", text)


def _replace_placeholders(command: str) -> list[str]:
    tokens = command.split()
    return [PLACEHOLDER_VALUES.get(token, token) for token in tokens[1:]]


def test_skill_files_exist() -> None:
    for path in SKILL_FILES:
        assert path.is_file(), f"missing skill file: {path}"


def test_skill_has_valid_frontmatter_and_discovery_description() -> None:
    frontmatter, text = _frontmatter(SKILL)

    assert frontmatter["name"] == "fecreator"
    assert re.fullmatch(r"[a-z0-9-]+", str(frontmatter["name"]))
    description = str(frontmatter["description"])
    assert description.startswith("Use when ")
    assert len(text.split("---", maxsplit=2)[1]) <= 1024
    assert "Fire Emblem GBA portrait" in description
    assert "manifest" not in description.lower()
    assert "tool" not in description.lower()


def test_skill_cli_examples_are_real_commands() -> None:
    parser = build_parser()
    examples = {example for path in SKILL_FILES for example in _cli_examples(_read(path))}

    assert examples
    for example in examples:
        parser.parse_args(_replace_placeholders(example))


def test_skill_references_only_real_mcp_tools() -> None:
    referenced = {
        token
        for path in SKILL_FILES
        for token in re.findall(r"`([a-z]+(?:_[a-z]+)+)`", _read(path))
    }

    assert referenced
    assert referenced <= set(TOOL_NAMES), (
        f"unknown MCP tools referenced: {referenced - set(TOOL_NAMES)}"
    )


def test_skill_stays_within_v1_portrait_scope_and_guardrails() -> None:
    skill_text = _read(SKILL)
    neutral_text = _read(PORTRAIT_NEUTRAL)
    combined = "\n".join(_read(path) for path in SKILL_FILES)

    workflows = set(re.findall(r'"workflow": "([^"]+)"', neutral_text))

    assert '"asset_type": "portrait"' in neutral_text
    assert '"target_spec": "fe-gba-portrait-standard"' in neutral_text
    assert workflows <= WORKFLOWS
    assert "ROM editor" in combined
    assert "review" in combined.lower()
    assert "validation" in combined.lower()
    assert "lineage" in combined.lower()
    assert "never edits pixels" in skill_text.lower()


def test_submit_sources_docs_limit_source_handoff_to_manual_flows() -> None:
    skill_text = _normalized(SKILL)
    gaps_text = _normalized(CAPABILITY_GAPS)
    neutral_text = _normalized(PORTRAIT_NEUTRAL)
    interfaces_text = _normalized(INTERFACES_DOC)

    assert "manual provider" in skill_text.lower()
    assert "source handoff" in skill_text.lower()
    assert "manual provider" in gaps_text.lower()
    assert "submit_sources" in gaps_text
    assert "`submit_sources`" not in neutral_text
    assert "submit_sources is the explicit source-handoff tool for manual/agent-owned files" in (
        interfaces_text.lower()
    )
    assert "gather or generate the requested sources, `submit_sources`" not in skill_text
    assert "`submit_sources` (for agent-owned image tools)" not in skill_text


def test_skill_docs_separate_job_build_from_standalone_validation() -> None:
    skill_text = _normalized(SKILL)
    neutral_text = _normalized(PORTRAIT_NEUTRAL)
    interfaces_text = _normalized(INTERFACES_DOC)

    assert "build_asset" in skill_text
    assert "already performs fail-closed target validation" in skill_text.lower()
    assert "existing package directory whose path the caller already knows" in skill_text.lower()
    assert 'provider": "fake"' in neutral_text.lower()
    assert "`validate_asset`" not in neutral_text
    assert "`build_asset`, then `validate_asset`" not in skill_text
    assert "`build_asset`, and `validate_asset`" not in neutral_text
    assert "build_asset" in interfaces_text.lower()
    assert "already runs target-spec validation" in interfaces_text.lower()
    assert "standalone validation of an existing package directory" in interfaces_text.lower()
