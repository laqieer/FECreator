# FECreator v1 public contract

This document freezes the FECreator **v1** public surface. Everything listed here
is covered by an executable freeze test — `tests/contracts/test_contract_freeze.py`
introspects the real models, routers, parsers, registries, and tool inventory, so
this page can never quietly drift away from the shipped code.

- Contract version: **`1.0`**
- Target specs: **`fe-gba-portrait-standard`**,
  **`fe8-dialogue-background-source-240x160`**
- Asset types: **`portrait`**, **`dialogue_background`**

Scope stays inside `docs/product-statement.md`: local-first portrait creation,
never a ROM editor and never a hosted generation service.

## 1. Frozen contract inventory

| Contract | Module | Wire version | Exported schema |
| --- | --- | --- | --- |
| `Manifest` | `fecreator.contracts.manifest` | `1.0` (inline `version` literal) | `schemas/manifest.schema.json` |
| `CandidateSnapshot` | `fecreator.contracts.review` | `1.0` (inline `version` literal) | `schemas/candidate.schema.json` |
| `JobResult` | `fecreator.contracts.result` | `1.0` (v1 surface) | `schemas/result.schema.json` |
| `LineageNode` | `fecreator.contracts.lineage` | `1.0` (v1 surface) | `schemas/lineage.schema.json` |
| `Diagnostic` | `fecreator.contracts.diagnostics` | `1.0` (v1 surface) | `schemas/diagnostics.schema.json` |
| `CapabilitySet` | `fecreator.contracts.capabilities` | `1.0` (v1 surface) | `schemas/capabilities.schema.json` |
| `DialogueBackgroundPackageManifest` | `fecreator.contracts.dialogue_background` | `1.0` (inline literals) | `schemas/dialogue_background_package.schema.json` |

`Manifest` and `CandidateSnapshot` carry `version: Literal["1.0"]` on the wire.
The remaining contracts have no inline discriminator; they are versioned by this
document and pinned by their exported schema plus the exact field sets below.

Every public contract model uses `ConfigDict(extra="forbid", frozen=True)`:
unknown fields are rejected at validation time and instances are immutable.
Sequences are tuples and mappings are frozen through `freeze_mapping()`.

## 2. Field signatures

### `Manifest`

| Field | Type | Default |
| --- | --- | --- |
| `version` | `Literal["1.0"]` | `"1.0"` |
| `asset_type` | `Literal["portrait", "dialogue_background"]` | required |
| `target_spec` | `Literal["fe-gba-portrait-standard", "fe8-dialogue-background-source-240x160"]` | required |
| `workflow` | `Literal["text_to_portrait", "concept_to_portrait", "expression_refine", "masked_variant", "text_to_dialogue_background", "concept_to_dialogue_background"]` | required |
| `provider` | `str` | required |
| `character_ref_pack` | `str \| None` | `None` |
| `character_ref_pack_rev` | `int \| None` (`>= 1`) | `None` |
| `parent_asset_id` | `str \| None` | `None` |
| `sources` | `tuple[SourceSpec, ...]` | `()` |
| `edit` | `EditSpec \| None` | `None` |
| `metadata` | `AssetMetadata \| None` | `None` |
| `params` | `Mapping[str, str \| int \| float \| bool]` | `{}` (frozen) |

- `SourceSpec`: `kind: Literal["text", "concept_art", "approved_portrait",
  "approved_dialogue_background"]`, `ref: str`.
- `EditSpec`: `mask_path: str`, `protected_regions: tuple[Region, ...]`.
- `Region`: `x >= 0`, `y >= 0`, `w > 0`, `h > 0`, `label: str`.
- `SourceIdentity`: non-empty `kind`, `id`, and `revision`.
- `AssetMetadata`: portable `name`, non-empty `purpose`, `source:
  SourceIdentity`, non-empty `license_note` and `source_note`, plus
  `requested_downstream_profile: Literal["fe8-dialogue-background-feimg2"] | None`.
- `Manifest.content_hash()` is the canonical manifest identity used by reports and bundles.

Cross-field rules (all fail loudly, never silently normalize):

1. `character_ref_pack_rev` requires `character_ref_pack`.
2. `edit` is only accepted when `workflow == "masked_variant"`.
3. `parent_asset_id` is **required** for `expression_refine` and `masked_variant`,
   and **rejected** for `text_to_portrait` and `concept_to_portrait`. It names the
   approved portrait or dialogue background a derived candidate is built from, and
   the build promotes it into `LineageNode.parents`, so
   `list_lineage_ancestors()` returns the approved base. A blank or whitespace-only
   value is rejected; surrounding whitespace on a real value is stripped.
4. `portrait` requires `fe-gba-portrait-standard`, one of its four established
   portrait workflows, and `metadata = null`; its package contract is unchanged.
5. `dialogue_background` requires
   `fe8-dialogue-background-source-240x160`, one of
   `text_to_dialogue_background`, `concept_to_dialogue_background`, or
   `masked_variant`, and non-null `metadata`.

### `DialogueBackgroundPackageManifest`

The published source-package manifest has these exact fields: `version`,
`contract_version`, `asset_type`, `asset_type_version`, `target_spec`,
`target_spec_version`, `name`, `purpose`, `width`, `height`, `opaque`,
`provider`, `model`, `prompt`, `reference_pack`, `reference_pack_rev`, `source`,
`png_sha256`, `license_note`, `source_note`, and
`requested_downstream_profile`. Its literals are `"1.0"` for all version fields,
`"dialogue_background"`, `"fe8-dialogue-background-source-240x160"`, `240`,
`160`, and `true`. `source` is `DialogueBackgroundSourceRecord` with `kind`,
`id`, `revision`, and lowercase SHA-256 `input_sha256`.

### `CandidateSnapshot`

`version` (`"1.0"`), `job_id`, `lineage_id`, `artifacts`, `diagnostics`,
`metrics`, `created_at`. Required: `job_id`, `lineage_id`, `artifacts`,
`created_at`. `created_at` must be a timezone-aware ISO-8601 timestamp.

### `JobResult` and `StageResult`

- `JobResult`: `job_id`, `ok`, `artifacts = ()`, `diagnostics = ()`, `lineage_id = None`.
- `StageResult`: `stage`, `ok`, `artifacts = ()`, `metrics = {}`, `diagnostics = ()`.
- `Artifact`: `role`, `path`, `sha256`, `media_type` (all required).

### `LineageNode`

`asset_id`, `operation`, `parents`, `provider`, `model`, `prompt`,
`reference_pack`, `reference_pack_rev`, `seed`, `params`, `mask`,
`protected_regions`, `metrics`, `approved_by`, `output_hashes`, `created_at`.
Required: `asset_id`, `operation`, `created_at`.

### `Diagnostic`

`code`, `severity`, `message`, `where = None`, `data = None`.
`severity` is `error | warning | info`. Contract violations are errors, never warnings.

## 3. Frozen enumerations

| Enumeration | Values |
| --- | --- |
| `Operation` | `import_concept`, `create_neutral`, `create_dialogue_background`, `import_dialogue_background_concept`, `refine_expression`, `variant_masked_edit`, `export_spec` |
| `Severity` | `error`, `warning`, `info` |
| `JobState` | `created`, `planning`, `waiting_for_provider`, `waiting_for_sources`, `processing`, `waiting_for_review`, `validating`, `completed`, `failed`, `cancelled` |
| `Capability` | `text_to_image`, `image_to_image`, `multi_reference`, `masked_edit`, `session_refinement`, `pose_control`, `lineart_control`, `identity_embedding`, `style_reference`, `seed_control`, `size_control`, `background_control`, `asynchronous_jobs` |

`COMPLETED`, `FAILED`, and `CANCELLED` are terminal. Invalid transitions raise
`InvalidTransitionError`; they are never coerced into a success-shaped result.

## 4. Registries

| Registry | Frozen v1 identifiers |
| --- | --- |
| Assets | `dialogue_background`, `portrait` |
| Target specs | `fe-gba-portrait-standard`, `fe8-dialogue-background-source-240x160` |
| Providers | `command`, `fake`, `manual`, `mcp-client` |

Registration is idempotent and guarded at import time; registries reject
duplicate identifiers.

## 5. Target spec: `fe-gba-portrait-standard`

Canonical output is exactly one opaque **128 x 112** indexed PNG plus one
same-basename JASC `.pal`:

- at most **16** GBA-snapped colors,
- background at palette index **0**,
- required background zones fully background, required slots non-empty.

Validation is fail-closed: any contract violation is an `error` diagnostic, and
`build_bundle()` refuses to publish. Compatibility evidence levels are described
in [`docs/febuilder-interop.md`](febuilder-interop.md); level 1 (deterministic,
ROM-free roundtrip) is mandatory and always runs in CI.

## 5a. Target spec: `fe8-dialogue-background-source-240x160`

Canonical output is one same-basename opaque **240 x 160** PNG plus
`<name>.manifest.json`. RGB, RGBA with every alpha value 255, and indexed `P`
PNG are accepted. The source contract intentionally has **no** color-count,
palette-index, palette-bank, tile, TSA, JASC-palette, compression, or ROM limit.
It fails closed for invalid geometry, non-opaque/corrupt PNGs, malformed or
hash-mismatched package metadata, unsafe paths, and missing required
source/license lineage. Lower-48-pixel composition guidance is warning-level.

`fe8-dialogue-background-feimg2` is an optional requested downstream profile,
not a source-validator rule. Optional downstream evidence may record an
FEBuilder command/result and reduced-image hash, palette/bank report, and
two-run TSA hashes; an explicitly configured external adapter failing prevents
that compatibility bundle from publishing. No built-in external FEBuilder or
expansion adapter exists, and an unconfigured optional adapter is `not_run`.

## 6. Workflow and provider capability semantics

| Workflow | Required capabilities | Preferred capabilities |
| --- | --- | --- |
| `text_to_portrait` | `text_to_image` | `seed_control` |
| `concept_to_portrait` | `image_to_image` | `multi_reference`, `style_reference` |
| `expression_refine` | `image_to_image` | `session_refinement` |
| `masked_variant` | `masked_edit` | `background_control` |
| `text_to_dialogue_background` | `text_to_image` | `seed_control`, `size_control` |
| `concept_to_dialogue_background` | `image_to_image` | `multi_reference`, `style_reference`, `size_control` |
| dialogue-background `masked_variant` | `masked_edit` | `background_control`, `size_control` |

Required expressions for a canonical portrait sheet: `neutral`,
`half_closed_eyes`, `closed_eyes`, `mouth1`, `mouth2`, `mouth3`.

Rules:

- A workflow declares its required capabilities and `require_capabilities()`
  raises `ProviderRefusal` when a provider is missing any of them. A missing
  capability is **never** silently downgraded to a lesser workflow.
- Preferred capabilities are advisory. Their absence never fails a job.
- Built-in providers: `fake` declares every capability (deterministic test
  output), `manual` declares `text_to_image`, `image_to_image`,
  `multi_reference`, and `masked_edit` (a human supplies the files), `command`
  and `mcp-client` are registered unconfigured with an empty capability set and
  refuse work until an operator configures them.
- `command` executes with `shell=False`, exchanges versioned JSON on stdin and
  stdout, runs under an allowlisted environment and a bounded timeout, and only
  accepts artifacts inside the job workspace. The same path, size, and redaction
  rules apply to `mcp-client` responses.

## 7. HTTP API

All JSON API routes are served under `/api`; the job event WebSocket lives at
`/ws/jobs/{job_id}` and the built web bundle is mounted at `/`. The application
publishes **no** OpenAPI, Swagger, or ReDoc endpoint (`openapi_url`, `docs_url`,
and `redoc_url` are `None`). `fecreator serve` binds loopback addresses only.

| Method | Path |
| --- | --- |
| GET | `/api/assets` |
| GET | `/api/specs` |
| GET | `/api/providers` |
| GET | `/api/jobs` |
| POST | `/api/jobs` |
| GET | `/api/jobs/{job_id}` |
| GET | `/api/jobs/{job_id}/candidate` |
| GET | `/api/jobs/{job_id}/approvals` |
| POST | `/api/jobs/{job_id}/plan-sources` |
| POST | `/api/jobs/{job_id}/sources` |
| POST | `/api/jobs/{job_id}/build` |
| POST | `/api/jobs/{job_id}/validate` |
| GET | `/api/jobs/{job_id}/artifacts/{relative_path:path}` |
| GET | `/api/jobs/{job_id}/report` |
| GET | `/api/jobs/{job_id}/bundle` |
| GET | `/api/jobs/{job_id}/bundle/{relative_path:path}` |
| POST | `/api/jobs/{job_id}/approve` |
| POST | `/api/jobs/{job_id}/reject` |
| POST | `/api/jobs/{job_id}/finalize` |
| POST | `/api/jobs/{job_id}/retry` |
| POST | `/api/jobs/{job_id}/cancel` |
| POST | `/api/validate` |
| GET | `/api/references` |
| GET | `/api/references/{pack_id}/history` |
| GET | `/api/lineage/{asset_id}` |
| GET | `/api/lineage/{asset_id}/ancestors` |
| GET | `/api/lineage/{asset_id}/children` |
| WEBSOCKET | `/ws/jobs/{job_id}` |

The additive build route calls the same `FeCreatorApp.build()` used by the CLI
and MCP tool. Expected failures return a diagnostic list, never a bare string.
The built web bundle is mounted at `/`; when it is missing the root route
answers `503` with the exact build command instead of a blank page.

## 8. JSON CLI

`fecreator <command>` writes one compact JSON document to stdout followed by a
single newline. Long options are never abbreviated.

```text
fecreator --version
fecreator list-assets
fecreator list-specs
fecreator list-providers
fecreator validate --spec <id> --path <dir>
fecreator job create --manifest <path>
fecreator job status <job-id>
fecreator job list
fecreator job candidate <job-id>
fecreator job approvals <job-id>
fecreator job plan-sources <job-id>
fecreator job validate <job-id>
fecreator job artifact <job-id> <package-relative-path>
fecreator job report <job-id>
fecreator job bundle <job-id>
fecreator job bundle-file <job-id> <bundle-relative-path>
fecreator job approve <job-id> --actor <actor>
fecreator job reject <job-id> --actor <actor> --reason <reason>
fecreator job finalize <job-id>
fecreator job retry <job-id> --actor <actor>
fecreator job cancel <job-id>
fecreator references list
fecreator references history <pack-id>
fecreator lineage get <asset-id>
fecreator lineage ancestors <asset-id>
fecreator lineage children <asset-id>
fecreator plan-sources --job <id> --out <dir>
fecreator submit-sources --job <id> --sources <dir>
fecreator build --job <id>
fecreator serve
```

Exit codes: `0` on success, `2` for expected failures (`validate` with any
`error` diagnostic, `build` with `JobResult.ok == false`, manifest/lookup/source
failures, a missing `FECREATOR_DATA_ROOT`, or a non-loopback `FECREATOR_HOST`).
`serve` is the only non-JSON command.

## 9. MCP tools

`build_mcp()` publishes exactly these tools:

```text
list_assets              list_specs                list_providers
list_jobs                create_job                get_job
get_job_candidate        list_approval_decisions   plan_sources
plan_job_sources         submit_sources            build_asset
validate_asset           validate_job              read_job_artifact
get_job_report           list_bundle_entries       read_bundle_file
list_reference_packs     list_reference_history    get_lineage
list_lineage_ancestors   list_lineage_children     approve_stage
reject_stage             approve_review            reject_review
finalize_job             retry_job                 cancel_job
```

Every tool routes through the same `FeCreatorApp` facade as the CLI and HTTP
adapters. Failures return `ok: false` with sanitized diagnostics and the MCP
`isError` flag; they never return success-shaped payloads.

## 10. Reference pinning and legacy unpinned jobs

`create_job()` pins the reference pack: when a manifest names a
`character_ref_pack` without a `character_ref_pack_rev`, the app resolves the
latest revision and stores the pinned revision on the persisted manifest. Every
persisted job therefore records exactly which immutable reference revision it
used.

Reading a **persisted** manifest that names a pack but has no revision is a
fail-closed error: `UnpinnedReferencePackError` is raised by both
`FeCreatorApp._reference_pack()` and `PortraitPlugin`. This is intentional and
applies to jobs written before pinning existed:

- such a job cannot be planned, built, or published,
- the failure is loud and never degrades into "use whatever revision is latest",
- the fix is to recreate the job, which pins the current revision.

`create_job()` maps reference failures to structured diagnostics on every
interface: a pack (or pinned revision) that does not exist is
`UNKNOWN_REFERENCE_PACK` (HTTP `404`, CLI exit `2`, MCP `isError`), and a visible
but corrupt pack is `CORRUPT_REFERENCE_PACK` (HTTP `409`, CLI exit `2`, MCP
`isError`). A `parent_asset_id` with no lineage node is `UNKNOWN_LINEAGE`
(HTTP `404`), refused before any provider runs. A corrupt job directory surfaces
as `CORRUPT_JOB` (HTTP `409`). No adapter discloses the absolute data root.

A **persisted** manifest for `expression_refine` or `masked_variant` without a
`parent_asset_id` fails closed the same way an unpinned reference pack does: the
job cannot be loaded, planned, or built, and the fix is to recreate it. This is
the final pre-v1 contract change, applied before the `1.0` surface is released.

### Corrupt persisted jobs

`JobStore.load()` distinguishes the two failures a job directory can present:

- the directory does not exist — the job is **missing**, reported as
  `UNKNOWN_JOB` (HTTP `404`, CLI exit `2`, MCP `isError`, WebSocket close
  `1008`);
- the directory exists but its `job.json` or `manifest.json` cannot be read as
  the current contract — the job is **corrupt**, reported as `CORRUPT_JOB`
  (HTTP `409`, CLI exit `2`, MCP `isError`, WebSocket close `1011`).

`JobCorruptionError` carries the offending job id as structured metadata, so
every adapter reports `where` = that job id. This holds for `list_jobs()` as well
as for direct reads, and for every adapter action that loads a job — not only
`get_job` / `job status`. The chained cause quotes absolute paths and is never
echoed; no adapter discloses the data root.

**Recovery is manual and fail-closed.** FECreator never migrates or reinterprets
a corrupt job:

1. back up `data/jobs/<job-id>` if anything in it is worth keeping (submitted
   sources, a candidate package, the event log),
2. remove the `data/jobs/<job-id>` directory,
3. recreate the job from a manifest that satisfies the current contract — which
   re-pins the reference revision and records the approved base.

Silently rewriting the persisted manifest would invent a lineage edge or a
reference revision that never existed, so it is not offered.

## 10a. Concurrency and lock contention

A build takes an exclusive sidecar **build lease** for its whole duration, claims
its job with a short locked transition to `processing`, releases the job lock
while the provider runs, and reacquires it only to publish the candidate or
record failure. Ordinary reads therefore stay responsive during a long provider
call, and a second build of the same job is refused explicitly with
`InvalidTransitionError` before it can reach the provider. The lease is released
by the operating system when its owner exits, so a build interrupted mid-flight
leaves a `processing` job that can simply be built again; it is never stranded.

Whatever lock contention remains is reported as a structured, redacted conflict:
diagnostic code `STORE_LOCK_TIMEOUT` with HTTP `409`, CLI exit `2`, MCP
`isError: true`, and WebSocket close code `1013`. `LockTimeoutError` is an
`OSError` subclass, so every adapter re-raises it ahead of its broad `OSError`
handling rather than reporting it as an operation-specific failure. The lock path
is never disclosed. The job event WebSocket performs its storage reads on a
worker thread, never on the event loop.

The build lease and the job lock are distinct failures. Only a failure to
*acquire* the lease means "a build is already running" (`InvalidTransitionError`);
a job-lock timeout raised from inside the lease — during the short claim or
publish transition — stays a `LockTimeoutError` and is reported as
`STORE_LOCK_TIMEOUT` like any other contention.

## 11. Compatibility policy

Within the `1.0` contract version:

- **Allowed** — adding a new *optional* field with a default; adding a new
  diagnostic `code`; adding a new provider, MCP tool, CLI command, or HTTP route;
  adding a new enumeration member that existing clients may ignore.
- **Breaking, requires a new contract version** — removing or renaming a field;
  making an optional field required; changing a field type; removing or renaming
  a literal, enumeration member, HTTP route, CLI command, or MCP tool; changing
  the meaning of an existing field.

Because every public contract sets `extra="forbid"`, a client that sends an
unknown field is rejected. A `version` value other than `"1.0"` is rejected by
`Manifest` and `CandidateSnapshot`, so a future contract revision cannot be
mistaken for this one.

This additive dialogue-background extension leaves the existing portrait
identifiers, portrait validation, and portrait package bytes unchanged.

When a Python public contract changes:

1. regenerate the committed exports with `export_schemas(Path("schemas"))`,
2. update `web/src/api/types.ts` when the UI consumes the contract,
3. run `pytest -q tests/contracts` and
   `npm run -w @laqieer/fecreator-web test -- src/api/types.contract.test.ts`,
4. update this document — the freeze test fails until the inventory matches.

## 12. Release gates

`.github/workflows/ci.yml` runs on every branch push and pull request. GitHub
Pages deployment is limited to successful `main` pushes and depends on all of
`python`, `web`, `browser`, `package`, `febuilder-interop`, and `secret-scan`.

| Job | Proves |
| --- | --- |
| `python` | Ruff, `ruff format --check`, strict mypy, and the full pytest suite on Linux and Windows for Python 3.11 and 3.12 |
| `web` | strict TypeScript, ESLint, Vitest, the local bundle build, and root-relative asset paths |
| `browser` | the Playwright local + demo end-to-end flows against a real `fecreator serve` and a real demo preview |
| `package` | `python -m build`, `twine check`, and `tests/test_package.py` (one `_web/index.html` per archive, wheel install smoke) |
| `febuilder-interop` | the mandatory deterministic ROM-free roundtrip, plus an opt-in configured-executable check when the `FEBUILDER_CLI` repository variable is set |
| `secret-scan` | ggshield on pushes to every branch and on same-repo pull requests |

No release gate requires a ROM, and none downloads one.
