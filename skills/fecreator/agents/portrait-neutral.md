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
4. For full execution, stay on MCP: `plan_sources`, gather or generate the requested
   sources, `submit_sources`, `build_asset`, and `validate_asset`.
5. Stop on validation errors. Report the diagnostics, keep the review history intact,
   and do not claim the package is ready.
6. Use `approve_stage` or `reject_stage` for review decisions so approvals and lineage
   stay recorded. Use `get_job` or `fecreator job status JOB_ID` for later status
   checks, and `cancel_job` if the work should be abandoned.
