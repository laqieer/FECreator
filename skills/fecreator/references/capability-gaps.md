# Capability and surface gaps

## Interface surface

The JSON CLI currently exposes only these real commands:

- `fecreator list-assets`
- `fecreator list-specs`
- `fecreator list-providers`
- `fecreator job create --manifest MANIFEST_PATH`
- `fecreator job status JOB_ID`
- `fecreator validate --spec fe-gba-portrait-standard --path PACKAGE_DIR`

If the task needs source planning, source submission, build, approval, rejection, or job
cancellation, switch to the MCP surface. Those actions exist only as MCP tools today.

## Workflow capability requirements

The workflow names below remain valid manifest vocabulary and provider-capability
targets, but only one build path is wired into the current portrait orchestration.

- Executable today: "text_to_portrait" and "concept_to_portrait".
- Unavailable until build orchestration exists: "expression_refine" and "masked_variant".

- "text_to_portrait" requires the provider capability "text_to_image".
- "concept_to_portrait" requires "image_to_image" and benefits from "multi_reference"
  plus "style_reference".
- "expression_refine" requires "image_to_image" and benefits from
  "session_refinement".
- "masked_variant" requires "masked_edit" and benefits from "background_control".

If a provider refuses because a required capability is missing, do not fake the missing
step. Choose another configured provider or use the manual provider with approved source
files and the MCP `submit_sources` source handoff.

When the human or agent will hand off files, create the job with provider `manual`
before `plan_sources` or `submit_sources`. Providers that generate their own outputs,
such as `fake`, external command, or MCP-client, should go straight to `build_asset`
instead of treating `submit_sources` as a generic generation step.
