---
name: fecreator
description: Use when a request is about creating, reviewing, or exporting a Fire Emblem GBA portrait in FECreator and the agent must stay inside the current JSON CLI or MCP surface.
---

# FECreator

FECreator owns imaging, review, validation, approvals, and lineage. This skill only
gathers intent, writes a manifest, and drives the real interface surface. It never edits pixels,
invents missing commands, bypasses review, bypasses validation, or bypasses lineage.

## Scope guardrails

- Support only the portrait v1 asset flow: asset type "portrait" and target spec
  "fe-gba-portrait-standard".
- Refuse or redirect requests that treat FECreator as a ROM editor, hosted generation
  service, or non-portrait asset tool.
- Keep workflow intake vocabulary inside the current portrait set: "text_to_portrait",
  "concept_to_portrait", "expression_refine", and "masked_variant".
- Executable today: "text_to_portrait".
- Unavailable until build orchestration exists: "concept_to_portrait",
  "expression_refine", and "masked_variant".

## Gather intent first

Capture:

- which portrait workflow fits the request
- the provider to use
- text, concept art, approved portrait, or manual uploads that will become sources
- whether a character reference pack or masked edit data is needed
- what review outcome the human expects before approval

## Real surface only

### CLI examples

Use the JSON CLI only for the commands that exist today:

- `fecreator list-assets`
- `fecreator list-specs`
- `fecreator list-providers`
- `fecreator job create --manifest MANIFEST_PATH`
- `fecreator job status JOB_ID`
- `fecreator validate --spec fe-gba-portrait-standard --path PACKAGE_DIR`

### MCP tools

Use only these MCP tools:

- `list_assets`
- `list_specs`
- `list_providers`
- `create_job`
- `get_job`
- `plan_sources`
- `submit_sources`
- `build_asset`
- `validate_asset`
- `approve_stage`
- `reject_stage`
- `cancel_job`

## Operating rules

1. If the task is still ambiguous, keep gathering intent until the manifest fields are
   concrete enough to write down.
2. Build a manifest and call `create_job`. For CLI usage, write the same manifest to a
   file and pass it to `fecreator job create --manifest MANIFEST_PATH`.
3. Use `plan_sources` to inspect the required inputs. Call `submit_sources` only for a
   manual provider source handoff: create the job with provider `manual` before
   `plan_sources` or `submit_sources`.
4. For providers that generate their own outputs (`fake`, external command, or
   MCP-client), do not insert `submit_sources` as a generic step. `build_asset`
   already performs fail-closed target validation for the job result.
5. Use `validate_asset` only for standalone validation of an existing package
   directory whose path the caller already knows.
6. Read diagnostics and job results exactly as returned. Explain capability gaps or
   validation failures instead of inventing a workaround.
7. Keep the human in the loop for approval. Use `approve_stage` or `reject_stage`
   instead of silently deciding.
8. If work should stop, use `cancel_job`. If the agent only needs job readback, use
   `get_job` or `fecreator job status JOB_ID`.

See `references/capability-gaps.md` for missing-capability handling and CLI/MCP surface
limits. See `agents/portrait-neutral.md` for a minimal neutral portrait recipe.
