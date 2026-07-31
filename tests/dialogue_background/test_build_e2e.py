from __future__ import annotations

from pathlib import Path

from fecreator.app import FeCreatorApp
from fecreator.contracts.manifest import AssetMetadata, Manifest, SourceIdentity, SourceSpec
from fecreator.core.config import Settings
from fecreator.jobs.model import JobState
from fecreator.specs.fire_emblem.gba.dialogue_background_source.spec import (
    Fe8DialogueBackgroundSource240x160,
)


def _metadata() -> AssetMetadata:
    return AssetMetadata(
        name="phantom_city",
        purpose="Original phantom city",
        source=SourceIdentity(kind="prompt", id="bg/phantom-city", revision="1"),
        license_note="Original repository fixture.",
        source_note="Generated from an original prompt.",
    )


def _fake_manifest() -> Manifest:
    return Manifest(
        asset_type="dialogue_background",
        target_spec="fe8-dialogue-background-source-240x160",
        workflow="text_to_dialogue_background",
        provider="fake",
        metadata=_metadata(),
        sources=(SourceSpec(kind="text", ref="phantom city"),),
        params={"width": 240, "height": 160},
    )


def test_fake_text_workflow_builds_reviewable_package(data_root: Path) -> None:
    app = FeCreatorApp(Settings(data_root=data_root))
    job = app.create_job(_fake_manifest())

    result = app.build(job.id)

    assert result.ok is True
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW
    package = data_root / "jobs" / job.id / "candidate" / "package"
    assert Fe8DialogueBackgroundSource240x160().validate(package) == []
    assert {path.name for path in package.iterdir()} == {
        "phantom_city.png",
        "phantom_city.manifest.json",
    }


def test_identical_inputs_produce_identical_candidate_package_bytes(data_root: Path) -> None:
    app = FeCreatorApp(Settings(data_root=data_root))
    first = app.create_job(_fake_manifest())
    second = app.create_job(_fake_manifest())

    assert app.build(first.id).ok is True
    assert app.build(second.id).ok is True

    first_package = data_root / "jobs" / first.id / "candidate" / "package"
    second_package = data_root / "jobs" / second.id / "candidate" / "package"
    for filename in ("phantom_city.png", "phantom_city.manifest.json"):
        assert (first_package / filename).read_bytes() == (second_package / filename).read_bytes()
