from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.lineage import LineageNode, Operation, Region


def test_region_fields() -> None:
    region = Region(x=0, y=0, w=96, h=80, label="face")

    assert (region.x, region.y, region.w, region.h, region.label) == (0, 0, 96, 80, "face")


@pytest.mark.parametrize(
    ("payload"),
    [
        {"x": -1, "y": 0, "w": 96, "h": 80, "label": "face"},
        {"x": 0, "y": -1, "w": 96, "h": 80, "label": "face"},
        {"x": 0, "y": 0, "w": 0, "h": 80, "label": "face"},
        {"x": 0, "y": 0, "w": 96, "h": 0, "label": "face"},
    ],
)
def test_region_rejects_out_of_bounds_values(payload: dict[str, int | str]) -> None:
    with pytest.raises(ValidationError):
        Region(**payload)


def test_lineage_node_immutable_and_defaults() -> None:
    node = LineageNode(
        asset_id="a1",
        operation=Operation.CREATE_NEUTRAL,
        created_at="2026-07-24T00:00:00+00:00",
    )

    assert node.parents == ()

    with pytest.raises((ValidationError, TypeError)):
        node.asset_id = "a2"


def test_operation_values() -> None:
    assert Operation.VARIANT_MASKED_EDIT.value == "variant_masked_edit"


def test_lineage_node_mapping_fields_are_immutable() -> None:
    node = LineageNode(
        asset_id="a1",
        operation=Operation.CREATE_NEUTRAL,
        params={"seed_locked": True},
        metrics={"score": 0.5},
        created_at="2026-07-24T00:00:00+00:00",
    )

    with pytest.raises(TypeError):
        node.params["other"] = False

    with pytest.raises(TypeError):
        node.metrics["other"] = 1.0


@pytest.mark.parametrize("created_at", ["not-a-date", "2026-07-24T00:00:00"])
def test_lineage_node_rejects_invalid_created_at(created_at: str) -> None:
    with pytest.raises(ValidationError):
        LineageNode(asset_id="a1", operation=Operation.CREATE_NEUTRAL, created_at=created_at)


def test_lineage_node_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LineageNode(
            asset_id="a1",
            operation=Operation.CREATE_NEUTRAL,
            created_at="2026-07-24T00:00:00+00:00",
            unexpected="value",
        )
