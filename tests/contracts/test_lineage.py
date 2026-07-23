from __future__ import annotations

import pytest
from pydantic import ValidationError

from fecreator.contracts.lineage import LineageNode, Operation, Region


def test_region_fields() -> None:
    region = Region(x=0, y=0, w=96, h=80, label="face")

    assert (region.x, region.y, region.w, region.h, region.label) == (0, 0, 96, 80, "face")


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
