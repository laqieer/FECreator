"""Executable freeze of the v1 public surface documented in ``docs/v1-contract.md``.

Every assertion here introspects the real models, routers, parsers, registries,
and tool inventory. Nothing matches prose, so the documentation can never drift
away from the shipped surface without this module failing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast, get_args, get_origin

import pytest
from fastapi import FastAPI
from fastapi.routing import APIWebSocketRoute
from pydantic import BaseModel

from fecreator.app import FeCreatorApp
from fecreator.assets.portrait.manifest import (
    PREFERRED_CAPS,
    REQUIRED_CAPS,
    REQUIRED_EXPRESSIONS,
    WORKFLOWS,
)
from fecreator.contracts.capabilities import Capability, CapabilitySet
from fecreator.contracts.diagnostics import Diagnostic, Severity
from fecreator.contracts.lineage import LineageNode, Operation, Region
from fecreator.contracts.manifest import EditSpec, Manifest, SourceSpec
from fecreator.contracts.result import Artifact, JobResult, StageResult
from fecreator.contracts.review import CandidateSnapshot
from fecreator.contracts.schemas import SCHEMA_MODELS
from fecreator.core.config import Settings
from fecreator.core.registry import PROVIDER_REGISTRY
from fecreator.interfaces import cli_json
from fecreator.interfaces.http_api import create_api
from fecreator.interfaces.mcp_server import make_handlers
from fecreator.jobs.model import JobState
from fecreator.providers.base import Provider, ProviderRefusal, require_capabilities
from fecreator.references.store import UnpinnedReferencePackError
from fecreator.specs.fire_emblem.gba.portrait_standard.layout import (
    BG_INDEX,
    MAX_COLORS,
    SHEET_H,
    SHEET_W,
)

V1_CONTRACT_VERSION = "1.0"

TARGET_SPEC_ID = "fe-gba-portrait-standard"
ASSET_TYPE_ID = "portrait"

FROZEN_MODELS: dict[str, type[BaseModel]] = {
    "Manifest": Manifest,
    "CandidateSnapshot": CandidateSnapshot,
    "JobResult": JobResult,
    "LineageNode": LineageNode,
}


def _literal_values(model: type[BaseModel], field_name: str) -> tuple[object, ...]:
    field = model.model_fields[field_name]
    annotation = field.annotation
    if get_origin(annotation) is not Literal:
        raise AssertionError(f"{model.__name__}.{field_name} is not a Literal")
    return get_args(annotation)


def _declared_version(model: type[BaseModel]) -> str:
    """Report the wire version a frozen public contract is published at.

    ``Manifest`` and ``CandidateSnapshot`` carry the version inline as a
    ``Literal`` discriminator. ``JobResult`` and ``LineageNode`` do not: they
    are versioned by the v1 surface itself, and their exact field signatures
    are frozen by the per-model assertions below.
    """
    if "version" not in model.model_fields:
        return V1_CONTRACT_VERSION
    values = _literal_values(model, "version")
    assert len(values) == 1, f"{model.__name__}.version must pin exactly one literal"
    return str(values[0])


def frozen_contract_inventory() -> dict[str, str]:
    return {name: _declared_version(model) for name, model in FROZEN_MODELS.items()}


def _fields(model: type[BaseModel]) -> tuple[str, ...]:
    return tuple(model.model_fields)


def _required_fields(model: type[BaseModel]) -> frozenset[str]:
    return frozenset(name for name, f in model.model_fields.items() if f.is_required())


# --------------------------------------------------------------------------
# Contract inventory and model configuration
# --------------------------------------------------------------------------


def test_v1_public_contract_inventory_is_frozen() -> None:
    assert frozen_contract_inventory() == {
        "Manifest": "1.0",
        "CandidateSnapshot": "1.0",
        "JobResult": "1.0",
        "LineageNode": "1.0",
    }


@pytest.mark.parametrize(
    "model",
    [
        Manifest,
        SourceSpec,
        EditSpec,
        CandidateSnapshot,
        JobResult,
        StageResult,
        Artifact,
        LineageNode,
        Region,
        Diagnostic,
        CapabilitySet,
    ],
)
def test_public_contract_models_forbid_extras_and_stay_frozen(model: type[BaseModel]) -> None:
    assert model.model_config.get("extra") == "forbid"
    assert model.model_config.get("frozen") is True


def test_exported_schema_inventory_is_frozen() -> None:
    assert set(SCHEMA_MODELS) == {
        "manifest",
        "result",
        "candidate",
        "diagnostics",
        "lineage",
        "capabilities",
    }
    assert SCHEMA_MODELS["manifest"] is Manifest
    assert SCHEMA_MODELS["result"] is JobResult
    assert SCHEMA_MODELS["candidate"] is CandidateSnapshot
    assert SCHEMA_MODELS["diagnostics"] is Diagnostic
    assert SCHEMA_MODELS["lineage"] is LineageNode
    assert SCHEMA_MODELS["capabilities"] is CapabilitySet


# --------------------------------------------------------------------------
# Field signatures
# --------------------------------------------------------------------------


def test_manifest_fields_and_defaults_are_frozen() -> None:
    assert _fields(Manifest) == (
        "version",
        "asset_type",
        "target_spec",
        "workflow",
        "provider",
        "character_ref_pack",
        "character_ref_pack_rev",
        "sources",
        "edit",
        "params",
    )
    assert _required_fields(Manifest) == {"asset_type", "target_spec", "workflow", "provider"}
    assert Manifest.model_fields["version"].default == V1_CONTRACT_VERSION
    assert Manifest.model_fields["character_ref_pack"].default is None
    assert Manifest.model_fields["character_ref_pack_rev"].default is None
    assert Manifest.model_fields["sources"].default == ()
    assert Manifest.model_fields["edit"].default is None


def test_manifest_literals_are_frozen() -> None:
    assert _literal_values(Manifest, "version") == (V1_CONTRACT_VERSION,)
    assert _literal_values(Manifest, "asset_type") == (ASSET_TYPE_ID,)
    assert _literal_values(Manifest, "target_spec") == (TARGET_SPEC_ID,)
    assert _literal_values(Manifest, "workflow") == (
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    )
    assert _literal_values(SourceSpec, "kind") == ("text", "concept_art", "approved_portrait")


def test_candidate_snapshot_fields_are_frozen() -> None:
    assert _fields(CandidateSnapshot) == (
        "version",
        "job_id",
        "lineage_id",
        "artifacts",
        "diagnostics",
        "metrics",
        "created_at",
    )
    assert _required_fields(CandidateSnapshot) == {
        "job_id",
        "lineage_id",
        "artifacts",
        "created_at",
    }
    assert _literal_values(CandidateSnapshot, "version") == (V1_CONTRACT_VERSION,)


def test_job_result_and_stage_result_fields_are_frozen() -> None:
    assert _fields(JobResult) == ("job_id", "ok", "artifacts", "diagnostics", "lineage_id")
    assert _required_fields(JobResult) == {"job_id", "ok"}
    assert _fields(StageResult) == ("stage", "ok", "artifacts", "metrics", "diagnostics")
    assert _required_fields(StageResult) == {"stage", "ok"}
    assert _fields(Artifact) == ("role", "path", "sha256", "media_type")
    assert _required_fields(Artifact) == {"role", "path", "sha256", "media_type"}


def test_lineage_node_fields_are_frozen() -> None:
    assert _fields(LineageNode) == (
        "asset_id",
        "operation",
        "parents",
        "provider",
        "model",
        "prompt",
        "reference_pack",
        "reference_pack_rev",
        "seed",
        "params",
        "mask",
        "protected_regions",
        "metrics",
        "approved_by",
        "output_hashes",
        "created_at",
    )
    assert _required_fields(LineageNode) == {"asset_id", "operation", "created_at"}
    assert _fields(Region) == ("x", "y", "w", "h", "label")


def test_diagnostic_fields_and_severities_are_frozen() -> None:
    assert _fields(Diagnostic) == ("code", "severity", "message", "where", "data")
    assert _required_fields(Diagnostic) == {"code", "severity", "message"}
    assert tuple(member.value for member in Severity) == ("error", "warning", "info")


# --------------------------------------------------------------------------
# Enumerations and registries
# --------------------------------------------------------------------------


def test_operation_enumeration_is_frozen() -> None:
    assert tuple(member.value for member in Operation) == (
        "import_concept",
        "create_neutral",
        "refine_expression",
        "variant_masked_edit",
        "export_spec",
    )


def test_capability_enumeration_is_frozen() -> None:
    assert tuple(member.value for member in Capability) == (
        "text_to_image",
        "image_to_image",
        "multi_reference",
        "masked_edit",
        "session_refinement",
        "pose_control",
        "lineart_control",
        "identity_embedding",
        "style_reference",
        "seed_control",
        "size_control",
        "background_control",
        "asynchronous_jobs",
    )


def test_job_state_enumeration_is_frozen() -> None:
    assert tuple(member.value for member in JobState) == (
        "created",
        "planning",
        "waiting_for_provider",
        "waiting_for_sources",
        "processing",
        "waiting_for_review",
        "validating",
        "completed",
        "failed",
        "cancelled",
    )


def test_registered_assets_specs_and_providers_are_frozen(data_root: Path) -> None:
    app = FeCreatorApp(Settings(data_root=data_root))

    assert app.list_assets() == [ASSET_TYPE_ID]
    assert app.list_specs() == [TARGET_SPEC_ID]
    assert app.list_providers() == ["command", "fake", "manual", "mcp-client"]


def _registered_provider(provider_id: str) -> Provider:
    return cast(Provider, PROVIDER_REGISTRY.get(provider_id))


def test_builtin_provider_capability_declarations_are_frozen() -> None:
    import fecreator.providers  # noqa: F401  (guarded import-time registration)

    assert _registered_provider("manual").capabilities.capabilities == frozenset(
        {
            Capability.TEXT_TO_IMAGE,
            Capability.IMAGE_TO_IMAGE,
            Capability.MULTI_REFERENCE,
            Capability.MASKED_EDIT,
        }
    )
    assert _registered_provider("fake").capabilities.capabilities == frozenset(Capability)
    # Registered but unconfigured: they must declare nothing until an operator
    # configures them, so no workflow can accidentally select them.
    assert _registered_provider("command").capabilities.capabilities == frozenset()
    assert _registered_provider("mcp-client").capabilities.capabilities == frozenset()


def test_a_provider_missing_a_required_capability_is_refused() -> None:
    unconfigured = _registered_provider("command")

    with pytest.raises(ProviderRefusal):
        require_capabilities(unconfigured, REQUIRED_CAPS["text_to_portrait"])

    require_capabilities(_registered_provider("fake"), REQUIRED_CAPS["masked_variant"])


# --------------------------------------------------------------------------
# Workflow and provider capability semantics
# --------------------------------------------------------------------------


def test_portrait_workflow_capability_semantics_are_frozen() -> None:
    assert frozenset(_literal_values(Manifest, "workflow")) == WORKFLOWS
    assert {
        "text_to_portrait": {Capability.TEXT_TO_IMAGE},
        "concept_to_portrait": {Capability.IMAGE_TO_IMAGE},
        "expression_refine": {Capability.IMAGE_TO_IMAGE},
        "masked_variant": {Capability.MASKED_EDIT},
    } == REQUIRED_CAPS
    assert {
        "text_to_portrait": {Capability.SEED_CONTROL},
        "concept_to_portrait": {Capability.MULTI_REFERENCE, Capability.STYLE_REFERENCE},
        "expression_refine": {Capability.SESSION_REFINEMENT},
        "masked_variant": {Capability.BACKGROUND_CONTROL},
    } == PREFERRED_CAPS
    assert REQUIRED_EXPRESSIONS == (
        "neutral",
        "half_closed_eyes",
        "closed_eyes",
        "mouth1",
        "mouth2",
        "mouth3",
    )


def test_target_spec_geometry_and_palette_limits_are_frozen() -> None:
    assert (SHEET_W, SHEET_H) == (128, 112)
    assert MAX_COLORS == 16
    assert BG_INDEX == 0


# --------------------------------------------------------------------------
# Interface operation inventories
# --------------------------------------------------------------------------


def _http_routes(api: FastAPI) -> set[tuple[str, str]]:
    """Read the served HTTP surface out of the generated OpenAPI document."""
    return {
        (method.upper(), path)
        for path, operations in api.openapi()["paths"].items()
        for method in operations
    }


def _websocket_routes(api: FastAPI) -> set[str]:
    return {route.path for route in api.routes if isinstance(route, APIWebSocketRoute)}


def test_http_route_inventory_is_frozen(data_root: Path) -> None:
    api = create_api(FeCreatorApp(Settings(data_root=data_root)))

    assert _http_routes(api) == {
        ("GET", "/api/assets"),
        ("GET", "/api/specs"),
        ("GET", "/api/providers"),
        ("GET", "/api/jobs"),
        ("POST", "/api/jobs"),
        ("GET", "/api/jobs/{job_id}"),
        ("GET", "/api/jobs/{job_id}/candidate"),
        ("GET", "/api/jobs/{job_id}/approvals"),
        ("POST", "/api/jobs/{job_id}/plan-sources"),
        ("POST", "/api/jobs/{job_id}/sources"),
        ("POST", "/api/jobs/{job_id}/validate"),
        ("GET", "/api/jobs/{job_id}/artifacts/{relative_path}"),
        ("GET", "/api/jobs/{job_id}/report"),
        ("GET", "/api/jobs/{job_id}/bundle"),
        ("GET", "/api/jobs/{job_id}/bundle/{relative_path}"),
        ("POST", "/api/jobs/{job_id}/approve"),
        ("POST", "/api/jobs/{job_id}/reject"),
        ("POST", "/api/jobs/{job_id}/finalize"),
        ("POST", "/api/jobs/{job_id}/retry"),
        ("POST", "/api/jobs/{job_id}/cancel"),
        ("POST", "/api/validate"),
        ("GET", "/api/references"),
        ("GET", "/api/references/{pack_id}/history"),
        ("GET", "/api/lineage/{asset_id}"),
        ("GET", "/api/lineage/{asset_id}/ancestors"),
        ("GET", "/api/lineage/{asset_id}/children"),
    }


def test_websocket_route_inventory_is_frozen(data_root: Path) -> None:
    api = create_api(FeCreatorApp(Settings(data_root=data_root)))

    assert _websocket_routes(api) == {"/ws/jobs/{job_id}"}
    assert api.url_path_for("job_events", job_id="job-1") == "/ws/jobs/job-1"


def test_nested_artifact_and_bundle_reads_keep_the_path_converter(data_root: Path) -> None:
    api = create_api(FeCreatorApp(Settings(data_root=data_root)))

    assert (
        api.url_path_for("read_job_artifact", job_id="job-1", relative_path="package/hero.png")
        == "/api/jobs/job-1/artifacts/package/hero.png"
    )
    assert (
        api.url_path_for("read_bundle_file", job_id="job-1", relative_path="package/hero.pal")
        == "/api/jobs/job-1/bundle/package/hero.pal"
    )


def test_http_api_publishes_no_schema_or_documentation_endpoints(data_root: Path) -> None:
    api = create_api(FeCreatorApp(Settings(data_root=data_root)))

    assert api.docs_url is None
    assert api.redoc_url is None
    assert api.openapi_url is None


def _cli_commands() -> set[str]:
    def walk(parser: object, prefix: str) -> set[str]:
        commands: set[str] = set()
        actions = getattr(parser, "_actions", [])
        subparser_actions = [action for action in actions if hasattr(action, "choices")]
        found = False
        for action in subparser_actions:
            choices = getattr(action, "choices", None)
            if not isinstance(choices, dict):
                continue
            for name, child in choices.items():
                found = True
                commands |= walk(child, f"{prefix} {name}".strip())
        if not found and prefix:
            commands.add(prefix)
        return commands

    return walk(cli_json.build_parser(), "")


def test_cli_command_inventory_is_frozen() -> None:
    assert _cli_commands() == {
        "list-assets",
        "list-specs",
        "list-providers",
        "validate",
        "job create",
        "job status",
        "job list",
        "job candidate",
        "job approvals",
        "job plan-sources",
        "job validate",
        "job artifact",
        "job report",
        "job bundle",
        "job bundle-file",
        "job approve",
        "job reject",
        "job finalize",
        "job retry",
        "job cancel",
        "references list",
        "references history",
        "lineage get",
        "lineage ancestors",
        "lineage children",
        "plan-sources",
        "submit-sources",
        "build",
    }


def test_mcp_tool_inventory_is_frozen(data_root: Path) -> None:
    handlers = make_handlers(FeCreatorApp(Settings(data_root=data_root)))

    assert set(handlers) == {
        "list_assets",
        "list_specs",
        "list_providers",
        "list_jobs",
        "create_job",
        "get_job",
        "get_job_candidate",
        "list_approval_decisions",
        "plan_sources",
        "plan_job_sources",
        "submit_sources",
        "build_asset",
        "validate_asset",
        "validate_job",
        "read_job_artifact",
        "get_job_report",
        "list_bundle_entries",
        "read_bundle_file",
        "list_reference_packs",
        "list_reference_history",
        "get_lineage",
        "list_lineage_ancestors",
        "list_lineage_children",
        "approve_stage",
        "reject_stage",
        "approve_review",
        "reject_review",
        "finalize_job",
        "retry_job",
        "cancel_job",
    }


# --------------------------------------------------------------------------
# Version and compatibility rules
# --------------------------------------------------------------------------


def test_manifest_rejects_unknown_versions_and_unknown_fields() -> None:
    payload = {
        "version": "1.1",
        "asset_type": "portrait",
        "target_spec": TARGET_SPEC_ID,
        "workflow": "text_to_portrait",
        "provider": "fake",
    }
    with pytest.raises(ValueError):
        Manifest.model_validate(payload)

    with pytest.raises(ValueError):
        Manifest.model_validate({**payload, "version": "1.0", "unknown": True})


def test_manifest_version_defaults_to_the_frozen_v1_value() -> None:
    manifest = Manifest(
        asset_type="portrait",
        target_spec=TARGET_SPEC_ID,
        workflow="text_to_portrait",
        provider="fake",
    )

    assert manifest.version == V1_CONTRACT_VERSION
    assert manifest.model_dump(mode="json")["version"] == V1_CONTRACT_VERSION


def test_legacy_unpinned_reference_jobs_fail_closed(data_root: Path) -> None:
    """A persisted manifest that names a pack without a revision must not load."""
    app = FeCreatorApp(Settings(data_root=data_root))
    unpinned = Manifest(
        asset_type="portrait",
        target_spec=TARGET_SPEC_ID,
        workflow="text_to_portrait",
        provider="fake",
        character_ref_pack="hero",
    )

    with pytest.raises(UnpinnedReferencePackError):
        app._reference_pack(unpinned)


def test_manifest_refuses_a_revision_without_a_pack() -> None:
    with pytest.raises(ValueError):
        Manifest(
            asset_type="portrait",
            target_spec=TARGET_SPEC_ID,
            workflow="text_to_portrait",
            provider="fake",
            character_ref_pack_rev=1,
        )


def test_manifest_refuses_an_edit_outside_masked_variant() -> None:
    with pytest.raises(ValueError):
        Manifest(
            asset_type="portrait",
            target_spec=TARGET_SPEC_ID,
            workflow="text_to_portrait",
            provider="fake",
            edit=EditSpec(mask_path="mask.png"),
        )
