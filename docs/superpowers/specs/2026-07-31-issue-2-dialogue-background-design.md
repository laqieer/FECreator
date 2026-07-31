# Issue #2 Dialogue Background Design

**Status:** Approved by the normative issue #2 contract and the autonomous completion objective

**Issue:** GitHub issue #2, `Add an FE8 240x160 dialogue-background source asset type`

## Context

FECreator currently has one asset plugin (`portrait`) and one target spec
(`fe-gba-portrait-standard`). Jobs, review decisions, lineage, reports, bundles,
CLI, HTTP, WebSocket, and MCP are mostly asset-neutral, but candidate orchestration
and final publication are still implemented inside portrait modules.

Issue #2 adds one static-art source workflow:

- asset type: `dialogue_background`
- target spec: `fe8-dialogue-background-source-240x160`
- workflows: `text_to_dialogue_background`,
  `concept_to_dialogue_background`, and `masked_variant`

The source contract ends at an opaque 240x160 PNG plus deterministic metadata.
Palette reduction, palette-bank assignment, TSA generation, compression, and ROM
integration remain downstream concerns.

## Goals

1. Add the dialogue-background asset, workflows, package, and target validator.
2. Accept opaque RGB, opaque RGBA, and indexed PNG inputs without a source color
   limit.
3. Produce deterministic package bytes for identical inputs on all supported
   platforms.
4. Reuse providers, jobs, review, lineage, reports, bundles, and every interface.
5. Remove the portrait-only finalization dependency from the application facade.
6. Preserve portrait package bytes and strict portrait validation.
7. Publish synchronized schemas, TypeScript types, and compatibility docs.

## Non-goals

- Built-in color reduction or palette-bank assignment
- TSA generation, compression, ROM insertion, or Makefile orchestration
- Animation, event timing, maps, sprites, or arbitrary image dimensions
- Shipping copyrighted FE8 assets
- Making the offline web demo generate dialogue backgrounds

## Considered approaches

### 1. Duplicate the portrait plugin lifecycle

Copy the portrait build, locking, review, and publication code into a new plugin.
This minimizes portrait edits but duplicates the most failure-sensitive code and
would allow the two assets to diverge under concurrency or rollback failures.

### 2. Branch inside the portrait plugin

Teach `PortraitPlugin` and portrait publication modules to handle both assets.
This is smaller initially, but leaves the application architecture explicitly
portrait-shaped and contradicts the acceptance criterion that shared flows work
without portrait assumptions.

### 3. Extract shared reviewed-asset orchestration

Move the common build lease, state transitions, candidate publication protocol,
and final publication into asset-neutral modules. Keep image preparation and
package assembly in separate portrait and dialogue-background plugins.

This is the selected approach. It changes more structure than duplication, but
it preserves one implementation of locking, approval, rollback, reporting, and
bundle publication while leaving target-specific validation isolated.

## Public contracts

`Manifest` remains version `1.0` and gains additive literals:

- `asset_type`: `portrait | dialogue_background`
- `target_spec`: `fe-gba-portrait-standard |
  fe8-dialogue-background-source-240x160`
- `workflow`: the four portrait workflows plus
  `text_to_dialogue_background` and `concept_to_dialogue_background`
- `SourceSpec.kind`: adds `approved_dialogue_background`

An optional `metadata` object is added to `Manifest`. It is required for
`dialogue_background` and rejected for portrait jobs. It contains:

- portable stable asset `name`
- non-empty `purpose`
- stable source identity (`kind`, `id`, `revision`)
- non-empty `license_note` and `source_note`
- optional requested downstream profile
  `fe8-dialogue-background-feimg2`

Manifest validation binds each asset to its target spec and supported workflows.
`masked_variant` continues to require `parent_asset_id` and `edit`; the dialogue
background variant additionally requires one approved-background source.

The canonical package metadata is a frozen, extra-forbidden public model:

```text
package/
  <name>.png
  <name>.manifest.json
```

The package manifest records contract, asset, and target versions; name and
purpose; geometry and opacity; provider/model/prompt/reference lineage; stable
source identity and a computed input hash; PNG SHA-256; license/source notes; and
the optional downstream profile. It intentionally contains no timestamp so
identical inputs produce identical bytes.

## Shared reviewed-asset orchestration

An asset-neutral reviewed-plugin base owns:

- the per-job cross-process build lease
- claimable-state checks
- pinned reference-pack loading
- provider execution outside the job lock
- failure transitions and diagnostics
- atomic candidate publication
- transition to `waiting_for_review`
- generic finalization through the registered target spec

Each concrete plugin supplies:

- capability declarations
- source planning
- workflow-specific preparation
- package assembly and candidate lineage

`FeCreatorApp.finalize_job()` dispatches to the job's asset plugin instead of
importing portrait publication directly.

Final publication copies exactly the candidate package described by the candidate
snapshot, revalidates it through `SPEC_REGISTRY`, writes the report and lineage,
builds the target-appropriate reproducibility bundle, and atomically transitions
the job through `validating` to `completed`.

## Dialogue-background workflows

### Text to dialogue background

The plugin requires `text_to_image`. It builds a prompt from text sources and
composition guidance, optionally supplies pinned reference-pack concept art, and
accepts exactly one selected background image artifact.

### Concept to dialogue background

The plugin requires `image_to_image` and at least one submitted or pinned concept
image. The selected provider result follows the same validation and canonical
package path as text generation.

### Masked variant

The plugin requires:

- an approved background PNG and matching package manifest
- a known parent lineage asset
- a black-and-white mask
- `masked_edit` capability

The provider proposes an edited full-size image. FECreator applies changes only
inside the mask, checks protected regions, and preserves all pixels outside the
mask. The result is then packaged as a new immutable background candidate.

Provider and submitted paths remain workspace-relative, hash-checked, regular
files. Unsafe paths, missing files, unsupported images, and hash mismatches fail.

## Deterministic image and package handling

Accepted source PNG modes are RGB, RGBA with every alpha value 255, and indexed
`P`. Other formats, corrupt PNGs, non-opaque pixels, and dimensions other than
240x160 fail.

All accepted input modes are normalized to one canonical RGB PNG encoding:

- PNG signature, IHDR, IDAT, and IEND only
- 8-bit RGB, filter type 0
- deterministic stored DEFLATE blocks
- no timestamps or environment-dependent metadata

This avoids platform-specific encoder choices and places no color-count,
palette-bank, indexed-PNG, or tile-count restriction on the source contract.
JSON metadata uses the repository's canonical sorted atomic writer.

The input hash is computed from the canonical manifest input plus the sorted
hashes and roles of submitted/reference artifacts actually consumed by the
workflow. It is not trusted from user input.

## Target validation

`Fe8DialogueBackgroundSource240x160` validates:

- the package directory exists and contains exactly one matching PNG/manifest pair
- the stable name is portable and matches both filenames
- metadata parses under the frozen public package model
- asset/spec/version identifiers are exact
- the PNG is valid, opaque, and exactly 240x160
- the recorded dimensions and opacity match the image
- the recorded PNG SHA-256 matches the file

It deliberately does not inspect source color count, palette banks, tile count,
or TSA compatibility. Composition and licensing guidance is documented and
represented in required metadata, not guessed from pixels.

## Reports and reproducibility bundles

Portrait bundles keep their existing deterministic FEBuilder-compatible roundtrip
evidence unchanged.

Dialogue-background bundles record deterministic source-package hash evidence:

- SHA-256 for both package files
- a `passed` source-contract status
- the requested downstream profile, if any
- external compatibility status `not_run` unless a future explicit adapter is
  configured

Bundle verification dispatches by manifest target spec. It compares the evidence
against the bundled package and never runs or requires portrait roundtrip logic
for dialogue backgrounds. An absent external FEBuilder/expansion adapter does not
invalidate the source package; a future explicitly configured adapter must fail
closed.

## Interface behavior

CLI, HTTP, WebSocket, and MCP keep their existing commands, routes, tools, JSON
shapes, error mapping, and application-facade calls. The additive manifest
literals and plugin/spec registries make the new asset available without new
interface-specific image logic.

The TypeScript API mirror gains the additive identifiers and metadata/package
types. Portrait controls and the deterministic offline demo remain portrait-only;
they must continue to reject unsupported demo behavior rather than making network
or filesystem calls.

## Error handling and security

- Target, workflow, metadata, and parent combinations fail during manifest
  validation.
- Missing required capabilities refuse before provider work.
- Provider artifacts must remain in the job workspace and match declared hashes.
- Submitted names are single portable filenames; symlinks and reparse points are
  rejected by existing source staging.
- Package validation is fail-closed for malformed metadata, unsafe names, missing
  files, opacity, dimensions, and hashes.
- Candidate and final publication retain atomic rollback semantics.
- No shell invocation, ROM access, or bundled copyrighted material is introduced.

## Testing and validation loop

1. Contract tests prove the new literals, metadata invariants, schema exports,
   TypeScript mirror, registries, operation values, and frozen model shapes.
2. Target-spec tests cover opaque RGB, opaque RGBA, indexed P, truecolor images
   with more than 128 colors, wrong dimensions, alpha, corrupt PNG, unsafe names,
   missing metadata, extra/missing files, and hash mismatch.
3. Workflow tests cover text, concept, and masked variant capability gates,
   workspace path/hash checks, protected regions, lineage parents, review, retry,
   and deterministic repeated package bytes.
4. CLI, HTTP, and MCP tests run a truecolor manual-provider job through build,
   approval, finalization, artifact reads, reports, and bundles.
5. Bundle tests prove dialogue-background hash evidence verifies independently
   and portrait compatibility evidence remains byte-for-byte unchanged.
6. Existing portrait tests and a canonical portrait package hash regression prove
   portrait package bytes did not change.
7. Run targeted Python and web contract tests, then the full Python and web CI
   commands and package build before closing issue #2.

## Delivery

Implementation is complete only when the branch is pushed, required checks pass,
the completing pull request is merged, and GitHub issue #2 is closed with the
merged change linked.
