# Neutral portrait recipe

Use this as a thin orchestration pattern for a standard neutral portrait request.

## Manifest skeleton

```json
{
  "asset_type": "portrait",
  "target_spec": "fe-gba-portrait-standard",
  "workflow": "text_to_portrait",
  "provider": "fake",
  "sources": [
    {
      "kind": "text",
      "ref": "young mage with short blue hair, neutral expression"
    }
  ],
  "params": {}
}
```

## Minimal flow

1. Confirm the request is still inside portrait v1 scope and gather missing source
   details.
2. Discover the current surface if needed with `list_assets`, `list_specs`, and
   `list_providers`.
3. Build the manifest, then call `create_job`. If the session is CLI-only, write the
   manifest file and run `fecreator job create --manifest MANIFEST_PATH`.
4. This recipe keeps provider `fake`, so stay on MCP and call `build_asset` directly.
   It covers generation, alignment, package export, and fail-closed target validation
   for the job result.
5. If the work instead needs a human or agent to hand off approved files, switch to a
   separate manual-provider source-handoff flow rather than treating this fake-provider
   recipe as a template for file submission.
6. Stop on validation errors. Report the diagnostics, keep the review history intact,
   and do not claim the package is ready.
7. Use `approve_stage` or `reject_stage` for review decisions so approvals and lineage
   stay recorded. Use `get_job` or `fecreator job status JOB_ID` for later status
   checks, and `cancel_job` if the work should be abandoned.
