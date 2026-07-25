# Issue #1 Completion Design

**Status:** Approved

**Issue:** GitHub issue #1, `Implement FECreator v1 portrait workbench`

## Context

FECreator already contains most of the v1 foundation:

- immutable jobs, approvals, events, reference packs, and lineage
- deterministic imaging and strict `fe-gba-portrait-standard` validation
- manual, fake, MCP-client, and external-command providers
- JSON CLI, FastAPI, WebSocket, MCP, reporting, and reproducibility bundles
- a React/Vite local and offline-demo shell

The remaining work is gap-driven. Existing, tested behavior stays in place unless
it must change to complete an issue requirement. The completion effort does not
replay already-finished master-plan tasks or expand beyond portrait-focused v1.

## Goals

1. Pin jobs to exact reference-pack revisions.
2. Orchestrate all four portrait workflows.
3. Make human review a real publication gate.
4. Complete the local React review and tuning flows.
5. prove deterministic ROM-free FEBuilder-compatible package behavior in CI.
6. Support optional local validation with an installed FEBuilderGBA CLI.
7. Stabilize and document the final v1 contracts.
8. Finish with green CI and close issue #1.

## Non-goals

- ROM editing, ROM storage, or ROM fixtures in CI
- hosted generation or public network access
- additional asset types or target specifications
- training, LoRA management, or a general-purpose pixel editor
- replacing the existing CLI, HTTP, WebSocket, MCP, report, or bundle architecture
- GitHub Releases

## Architecture

`FeCreatorApp` remains the single application facade. Every interface calls the
facade and contains no image-processing, persistence, or workflow rules.

```text
CLI / HTTP / WebSocket / MCP / React / skills
                         |
                         v
                   FeCreatorApp
                         |
         +---------------+----------------+
         |               |                |
     job service   reference/lineage   portrait plugin
                                          |
                           workflow-specific preparation
                                          |
                              deterministic processing
                                          |
                               review-gated publication
                                          |
                         target validation/report/bundle
```

The portrait plugin is split into small workflow-specific preparation units and
shared candidate/publication units. Target layout, palette, assembly, and strict
package validation remain under
`specs/fire_emblem/gba/portrait_standard`.

## Reference-pack revision pinning

The manifest gains an optional reference-pack revision paired with
`character_ref_pack`.

At job creation:

1. A manifest without a reference-pack ID keeps both fields unset.
2. A manifest with an ID and no revision resolves the latest visible revision.
3. A manifest with both values validates that exact revision.
4. The resolved manifest snapshot, including the revision, is persisted in the job.

Planning, generation, retries, reporting, and lineage load the exact pinned
revision with `ReferencePackStore.get()`. They never call `latest()`.

A revision without an ID is invalid. A legacy persisted job that names a pack but
has no revision fails with an explicit unpinned-reference diagnostic instead of
silently adopting newer reference data.

The application facade exposes read-only reference-pack history and lineage
queries needed by the web workbench. Store path containment, locks, immutable
revision files, and corruption behavior remain unchanged.

## Portrait workflow orchestration

Every workflow validates required source kinds and provider capabilities before
entering processing. Missing requirements refuse the workflow without fallback.

### Text to portrait

The existing path remains the baseline:

1. Build prompts from text and the pinned reference pack.
2. Request a neutral portrait from a `text_to_image` provider.
3. Align and process the neutral image deterministically.
4. Assemble a reviewable candidate package.

### Concept to portrait

This workflow requires concept-art input from submitted sources or the pinned
reference pack and an `image_to_image` provider.

The provider receives the concept references and prompt plan. The returned
neutral candidate then follows the same deterministic alignment, palette,
assembly, and validation path as text-to-portrait.

### Expression refinement

This workflow requires an approved portrait package and an `image_to_image`
provider.

The approved base portrait is preserved. Generated expression cells are applied
with the existing patch-border invariance helpers, assembled into the canonical
sheet, and validated against expression completeness and protected geometry.

### Masked variant

This workflow requires an approved portrait, a mask, protected regions, and a
`masked_edit` provider.

The provider proposes an edited image. The deterministic variant helper applies
changes only inside the mask, checks protected regions, and rejects shape,
boundary, or protected-region violations before package assembly.

### Source safety

Provider artifacts and submitted files are accepted only from the job workspace.
Manifest references are resolved through application-owned storage identifiers;
they are not arbitrary filesystem reads. Existing size, image, path, and
redaction budgets apply to every workflow.

## Review-gated publication

Generation writes an immutable candidate inside the job workspace and records
its diagnostics and metrics. A structurally invalid candidate fails before
review. A valid candidate transitions the job to `waiting_for_review`.

The review stage is canonical for the candidate associated with that immutable
job revision:

- approval records the actor and permits finalization
- rejection records a required reason and preserves all candidate evidence
- a retry creates a new immutable job or asset revision linked to the rejected
  candidate rather than overwriting it

Finalization requires an approval record for the current candidate. It reruns
strict target validation, then atomically publishes the canonical package,
report, reproducibility bundle, and lineage node. Publication uses the existing
rollback hooks so a partial report, bundle, package, or lineage write cannot look
successful.

Automated quality diagnostics remain fail-closed. Human approval does not bypass
unsafe paths, missing capabilities, protected-region errors, package contract
errors, or target validation failures.

## Application and interface behavior

The existing interface implementations stay thin and equivalent. The facade
adds the read and action methods required by the workbench:

- list jobs and inspect a job's current candidate
- plan and submit sources
- run or resume workflow processing
- approve or reject the current review stage
- list events and approval decisions
- list reference packs and revisions
- query lineage parents, children, and ancestry
- validate and inspect the final package, report, and bundle

HTTP endpoints mirror these facade operations with structured diagnostics.
CLI and MCP commands preserve their JSON and tool-result conventions. Existing
tool names remain stable unless a new operation is strictly required.

The WebSocket stream continues to derive from persisted job events. Review,
validation, approval, rejection, and publication transitions therefore appear
consistently in CLI, HTTP, MCP, and web views.

## React workbench

The web application keeps its current composition boundary:

- local mode uses HTTP and WebSocket adapters
- demo mode uses deterministic in-memory fixtures and timers
- demo mode performs no fetch, WebSocket, upload, persistence, or filesystem calls

The completed local workbench includes:

- a job/project dashboard and queue
- manifest, workflow, provider, and reference-pack controls
- source planning and submission status
- candidate review with approve and reject actions
- mask and protected-region editing for masked variants
- native-size, palette, expression-cell, and target-overlay previews
- package validation diagnostics
- reference revision and lineage history
- report and reproducibility-bundle inspection/export

Existing accessible status, loading, and error patterns remain in use. Actions
must update persisted backend state; placeholder callbacks and static lineage or
reference data are removed.

## FEBuilder interoperability

CI always runs a deterministic, ROM-free compatibility probe against a synthetic
canonical package. The probe:

1. validates the package with `fe-gba-portrait-standard`
2. decodes the indexed PNG and matching JASC palette
3. verifies the documented FEBuilder portrait dimensions, palette ordering,
   transparent/background index, cell geometry, and patch borders
4. performs a deterministic decode/re-encode round trip
5. compares pixels, palette entries, and canonical hashes

This probe is mandatory and cannot silently skip.

An optional local adapter runs a configured FEBuilderGBA CLI argv with
`shell=False`, a bounded timeout, an allowlisted environment, and redacted,
bounded output. If no executable is configured, the result is explicitly
`not_run`; it does not weaken the mandatory built-in compatibility probe. A
configured executable returning nonzero fails that explicit validation.

Documentation distinguishes deterministic compatibility evidence from optional
validation by the actual external executable. ROM-required checks remain opt-in,
local-only, and outside CI.

## Contracts and compatibility

The reference-pack revision and any candidate/review read models are finalized
before declaring v1 frozen.

For each public Python contract change:

- export the committed JSON Schema
- update the TypeScript mirror when consumed by the UI
- verify Python and TypeScript contract parity

`docs/v1-contract.md` identifies the frozen public contracts, interface names,
version fields, and compatibility policy. A regression test verifies the
committed v1 contract surface so later accidental field, enum, route, or tool
changes fail visibly.

Legacy unpinned reference jobs are the only intentionally unsupported persisted
shape. They fail with actionable diagnostics because replaying them against the
latest pack would violate reproducibility.

## Error handling and security

The completion work preserves current fail-closed behavior:

- invalid state transitions and duplicate approvals raise explicit errors
- missing workflow inputs or required capabilities refuse before provider work
- provider diagnostics are bounded and redacted
- provider and external-tool execution never uses a shell
- unsafe, external, symlinked, or reparse-point paths are rejected
- malformed masks, images, palettes, packages, and protected regions fail
- failed validation cannot publish final artifacts
- atomic publication rolls back all newly visible outputs on failure
- manifests, reports, bundles, tests, and logs contain no credentials or private art

The server remains bound to `127.0.0.1` by default.

## Testing

### Python

- manifest validation and schema export for reference revision pinning
- reference-store exact-revision and legacy-unpinned behavior
- each workflow's inputs, capability refusal, provider request, deterministic
  processing, candidate creation, review gate, and final publication
- rejection, retry lineage, rollback, corruption, and path containment
- HTTP, CLI, MCP, WebSocket, and app equivalence for new operations
- mandatory deterministic FEBuilder compatibility probe
- optional external CLI success, unavailable, timeout, redaction, and nonzero cases
- v1 contract freeze and packaging tests

### Web

- component tests for dashboard, controls, review actions, mask editing,
  validation, lineage, references, and export
- local adapter tests for all new API operations
- demo tests proving deterministic offline behavior
- Playwright flows covering job creation through approved package export and a
  rejected masked-variant path

### CI and packaging

CI runs the existing Ruff, formatting, mypy, pytest, web typecheck, lint, unit
tests, package build, and secret scanning, plus browser end-to-end and mandatory
interop jobs. Web assets are built before the Python distribution.

The existing MCP redaction regression is fixed as part of this effort. No issue
item is complete while a required GitHub Actions check is failing.

## Delivery

Implementation uses focused commits. Each commit is pushed immediately, and CI
is monitored asynchronously so further work can continue while checks run.
Failures are fixed and pushed until all required checks are green.

After acceptance:

1. Update issue #1's checklist to reflect the completed implementation.
2. Link the completing commits or pull request.
3. Close issue #1.
4. Do not create a GitHub Release.

## Acceptance criteria

Issue #1 is complete when:

- reference packs and lineage are versioned, queryable, and replay-safe
- all four portrait workflows execute through the application facade
- final publication requires human approval
- `fe-gba-portrait-standard` packages pass strict validation and the mandatory
  deterministic compatibility probe
- optional configured FEBuilderGBA validation is supported safely
- the local React workbench provides real review and tuning flows
- thin skills continue to use CLI or MCP without bypassing gates
- end-to-end browser and backend workflows pass
- v1 contracts and documentation are frozen and synchronized
- package builds and every required CI check are green
- issue #1 is updated and closed
