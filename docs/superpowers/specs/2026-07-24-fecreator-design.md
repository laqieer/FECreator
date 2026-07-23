# FECreator v1 Design

**Approved source:** FEBuilderGBA Discussion #2007, comment `17754379`.

The current implementation request is the explicit approval to resume from
that cross-PC architecture handoff.

## Product

FECreator is a local-first, agent-neutral, provider-neutral Fire Emblem asset
creation workbench with deterministic processing, human review, target
specifications, and reproducible asset lineage.

It is not a ROM editor, ROM builder, FEBuilderGBA replacement, hosted
generation service, or generic non-Fire-Emblem asset tool.

## Version 1 scope

- Backend: Python 3.11+, FastAPI, Pydantic, NumPy, OpenCV.
- Frontend: TypeScript, React, Vite, Konva.
- Runtime: local FastAPI server bound to `127.0.0.1` plus the system browser.
- Agent interfaces: JSON CLI, MCP server, and thin skills.
- Providers: manual submission, deterministic fake, generic MCP client, and
  an approved external command using JSON stdin/stdout without a shell.
- Asset plugin: `portrait`.
- Target spec: `fe-gba-portrait-standard`.
- Workflows:
  - text to neutral portrait
  - concept/reference art to neutral portrait
  - approved portrait to expression refinements
  - approved portrait to non-destructive masked variant

Deferred: unit icons, map sprites, battle sprites, multi-frame weapon edits,
LoRA training, other FE platforms, and full painting/pixel-editor tooling.

## Architecture

```text
Human or agent interface
        |
        v
Persistent application/job service
        |
        v
Asset plugin + target specification
        |
        v
Provider bridge or submitted sources
        |
        v
Deterministic NumPy/OpenCV processing
        |
        v
Validation, review, package, and lineage
```

All interfaces call one application service. Interface adapters contain no
image-processing logic.

Asset plugins own semantic workflows. Target specifications own concrete
dimensions, palettes, layouts, assembly, and format validation.

## Persistent jobs and lineage

Job states:

```text
created
planning
waiting_for_provider
waiting_for_sources
processing
waiting_for_review
validating
completed
failed
cancelled
```

Jobs persist manifest snapshots, reference-pack revisions, capability
decisions, prompts, sources, masks, protected regions, outputs, approvals,
events, diagnostics, and final results. Jobs resume after process exit.

Accepted sources, approved stages, exports, and asset revisions are immutable.
Changes create explicit new revisions. Assets form a directed acyclic lineage
graph and never overwrite parents.

## Provider behavior

Providers declare capabilities such as `text_to_image`, `image_to_image`,
`multi_reference`, `masked_edit`, `seed_control`, and `asynchronous_jobs`.
Workflows declare required and preferred capabilities.

Missing required capabilities cause a refusal. There is no silent downgrade.
Credentials remain in environment variables, OS keyring, or provider-owned
configuration and never enter manifests or bundles.

The command provider executes an argv list with `shell=False` and exchanges
versioned JSON over stdin/stdout.

## Imaging

NumPy/OpenCV own quality-critical work:

- illustration, nearest-neighbor, pseudo-pixel-grid, and manual-grid resizing
- connected masks, components, morphology, holes, distance transforms, and
  halo cleanup
- deterministic LAB k-means and weighted median-cut quantization
- locked/protected colors and shared palettes
- bounded nearest-palette mapping and resource budgets
- similarity, protected-region, silhouette, palette, and drift metrics

Pillow is restricted to image decode, encode, metadata, and compatibility.
Low-confidence grid detection and failed quality thresholds stop for review.

## FE GBA portrait target

Target ID: `fe-gba-portrait-standard`.

Canonical package:

- one `128x112` indexed PNG
- at most 16 GBA-snapped colors
- background at palette index 0
- a same-basename matching JASC palette
- FE-Repo Standard hackbox geometry

Slots:

| Slot | X | Y | Size |
| --- | ---: | ---: | --- |
| Main portrait | 0 | 0 | 96x80 |
| Mini portrait | 96 | 16 | 32x32 |
| Half-closed eyes | 96 | 48 | 32x16 |
| Closed eyes | 96 | 64 | 32x16 |
| Mouths 1-4 | 0, 32, 64, 96 | 80 | 32x16 each |
| Mouths 5-7 | 0, 32, 64 | 96 | 32x16 each |

The target spec fails closed on bad dimensions, palette drift, unsafe zones,
missing cells, background holes, dark foreground loss, broken patch borders,
or PNG/JASC mismatch.

Normal CI proves ROM-free interoperability with:

```text
FEBuilderGBA.CLI --validate-asset --kind=portrait-package --path=<dir>
FEBuilderGBA.CLI --import-asset --kind=portrait-package --path=<src> --out=<dst>
FEBuilderGBA.CLI --roundtrip-asset --kind=portrait-package --path=<src> --expect=<baseline>
```

ROM import/build checks require an explicit, user-owned, validated fixture and
remain opt-in local acceptance tests.

## Human and agent interfaces

The CLI and MCP server expose registry discovery, job lifecycle, source
planning/submission, generation, build, validation, inspection, approval,
rejection, and cancellation.

The local web workbench includes a project dashboard, reference board,
manifest/provider controls, job timeline, candidate gallery, target overlays,
mask and protected-region editing, palette/native-size preview, eye/mouth
review, lineage/variants, approval controls, and export report.

Skills only gather intent, create manifests, call CLI/MCP, explain capability
gaps, and guide review. They cannot reimplement processing or bypass gates.

## Security and privacy

- Bind only to `127.0.0.1` by default; no public tunnel.
- Constrain every path to its job workspace.
- Require explicit approval before remote provider uploads.
- Show which prompts/references leave the machine.
- Redact credentials and signed URLs.
- Preserve originals and immutable revisions.
- Enforce pixel, memory, histogram, upload, and cancellation budgets.
- Use original or synthetic fixtures; do not copy unlicensed implementation
  code or artwork.

## Testing

Cover contracts and registries, job transitions and recovery, containment and
secret redaction, deterministic hashing, interrupted writes, imaging golden
cases, grid confidence, quantizer determinism, masks and resource budgets,
portrait/variant workflows, protected-region invariance, CLI/MCP/HTTP
equivalence, GUI component/browser flows, provider refusal/cancellation, bundle
reproducibility, and ROM-free FEBuilderGBA interoperability.

## Distribution

Ship one Python distribution named `fecreator` containing prebuilt private
React assets. Provide `fecreator` CLI/MCP/server entry points and support
isolated installation with `pipx`. Do not create GitHub Releases.
