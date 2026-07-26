# Task 9 Report: Live Job Dashboard and Manifest Controls

## Status

Completed on 2026-07-27. The Task 9 implementation is in commit
`ec4eda3ec2c5d7e6b27fad04d56d0cf8ee127305`, pushed to
`origin/issue-1-completion`.

## RED/GREEN Evidence

- **RED:** The focused component run failed as expected before production implementation:
  missing `JobQueue`, `ManifestControls`, and `SourceStatus` modules, and no persisted-job
  queue in `App`.
- **GREEN:** The focused run passed **5 files / 10 tests** after implementation.
- **Final verification:** `typecheck`, `lint`, and the full web suite passed:
  **28 files / 72 tests**.

## State and Data Flow

- `useWorkbench(api, events)` owns the sorted persisted-job list, selected job/candidate,
  source plan, action state, errors, mutations, and injected event subscription.
- It loads the initial deterministic queue, loads a selected job and candidate, refreshes after
  source mutations and event snapshots, and retains the selected ID through an eventually
  consistent refresh.
- `App` keeps composition injection intact, fetches registries/reference history, and supplies
  the controller's live data to the queue, controls, source status, timeline, review, reference,
  mask, and existing tab surfaces.
- `ManifestControls` emits only exact v1 portrait manifests: fixed v1 asset/spec, a selected
  provider/workflow/reference revision, validated scalar JSON params, sources, and validated
  masked-edit regions.
- `SourceStatus` remains presentational; it forwards planned-source and selected-local-file
  actions to the controller, which calls `ApiClient`.

## Accessibility and Demo Behavior

- The queue is an explicitly labelled list of pressed-state buttons and announces loading,
  errors, and empty state with existing status/alert patterns.
- Existing roving tab keyboard behavior, panel labelling, timeline status, and lazy mask-editor
  fallback remain covered.
- Demo continues to use the injected deterministic in-memory client/event source; its integration
  test confirms no `fetch` or `WebSocket` calls.

## Tests and Results

```text
npm run -w @laqieer/fecreator-web typecheck  # passed
npm run -w @laqieer/fecreator-web lint       # passed
npm run -w @laqieer/fecreator-web test       # passed: 28 files, 72 tests
```

Focused component coverage was added for job selection, queue states, exact manifest creation,
parameter validation, source planning/local-file submission, and workbench job loading.

## Files Changed

- Added `web/src/workbench/useWorkbench.ts`
- Added `web/src/dashboard/JobQueue.tsx` and tests
- Added `web/src/controls/ManifestControls.tsx`, `SourceStatus.tsx`, and tests
- Updated `App`, its integration tests, lazy-mask test, root composition test, and injected event
  hook support.

## Self-Review, Deviations, and Concerns

- Checked the complete diff for whitespace and reviewed state transitions, event refresh behavior,
  nullable selections, exact manifest constraints, and demo isolation.
- No deviations from the brief. No Python contract changes were needed.
- Candidate artifact rendering remains limited to passing live candidate artifact data into the
  pre-existing review surface; blob retrieval/review actions remain intentionally out of Task 9
  scope.

## Task 9 Review-Finding Fix Evidence (2026-07-27)

### RED

- `SourceStatus` retained Job A's selected files after changing to Job B; its new regression
  test failed because the submit button remained enabled.
- The focused artifact test initially failed to resolve the absent `useCandidateArtifactUrls`
  module, proving candidate paths were not being fetched through `ApiClient.getArtifact`.

### GREEN

- Added selection identity guards around asynchronous job and candidate requests. The workbench
  now ignores stale completions and refreshes queue, selected job, and candidate state after a
  selected-job event snapshot.
- Added focused regression coverage for out-of-order job loads and selected-job event refresh.
- Added `sourceError` ownership to `useWorkbench`, passed it to `SourceStatus`, and clear it only
  after source-operation success or a selection change. Source-file state and its file input now
  reset per job.
- Added `useCandidateArtifactUrls`: it obtains image blobs through `ApiClient.getArtifact`,
  exposes accessible loading/error state, and revokes object URLs on replacement, failure, stale
  resolution, and unmount. Demo continues to receive in-memory blobs through its existing client.
- Focused verification passed: **6 files / 16 tests**:

```text
npm run -w @laqieer/fecreator-web test -- src/app/App.test.tsx src/app/App.workbench.test.tsx src/dashboard/JobQueue.test.tsx src/controls/ManifestControls.test.tsx src/controls/SourceStatus.test.tsx src/review/useCandidateArtifactUrls.test.tsx
```

- Final verification passed: `typecheck`, `lint`, and the full web suite
  (**29 files / 78 tests**).

### Self-Review

- Confirmed no raw candidate artifact path is assigned as an image URL.
- Confirmed stale job, candidate, and blob responses cannot alter the newly selected view.
- Kept artifact retrieval limited to the review-image boundary; no Task 10 review actions were
  introduced.

## Task 9 Remaining-Finding Fix Evidence (2026-07-27)

### RED

- `demoClient.test.ts` failed when `getArtifact(created.id, "candidate/package/portrait.png")`
  looked up a candidate artifact that was not stored in the demo blob map.
- `AppRoot.test.tsx` could not render the seeded candidate review image in demo mode because the
  image URL never resolved.
- `ManifestControls.test.tsx` accepted a protected-region object with an extra key, so the UI
  could emit a manifest that the Python `Region` model would reject.

### GREEN

- Demo candidate blobs now use the exact backend-relative candidate artifact path, and newly
  submitted demo candidates populate their artifact bytes under those same paths.
- The demo App regression now renders `Candidate candidate/package/portrait.png` without network
  or socket traffic.
- `ManifestControls` now rejects protected regions unless they have exactly `x`, `y`, `w`, `h`,
  and `label`, with integer/nonnegative `x/y`, positive integer `w/h`, and a non-empty label.
- Focused verification in the worktree passed:

```text
npm run -w @laqieer/fecreator-web test -- src/app/AppRoot.test.tsx src/demo/demoClient.test.ts src/controls/ManifestControls.test.tsx
```

- Final verification in the worktree passed:

```text
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
```

## Task 9 Final Finding Fix Evidence (2026-07-27)

### RED

- `demoClient.test.ts` now asserts the demo candidate artifact is a real PNG. The test failed
  before the fix because `candidate/package/portrait.png` contained plain text bytes beginning with
  `demo can`, not the PNG signature.
- `AppRoot.test.tsx` still verified demo mode loaded the review image through an object URL with no
  network calls.

### GREEN

- Demo artifact storage now returns deterministic synthetic PNG bytes for both seeded and generated
  candidate/final portrait artifacts, while keeping the exact candidate path and offline Blob flow.
- Added a regression test that checks the PNG signature and IHDR chunk directly from the demo
  Blob.
- Strengthened the AppRoot regression to confirm the object URL is created from an `image/png`
  Blob.
- Verification passed:

```text
npm run -w @laqieer/fecreator-web test -- src/demo/demoClient.test.ts src/app/AppRoot.test.tsx
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
```

## Task 9 Demo PNG Integrity Fix Evidence (2026-07-27)

### RED

- `demoClient.test.ts` now parses the full PNG structure and recomputes CRCs.
- The old embedded `candidate/package/portrait.png` bytes failed that regression because the IDAT
  CRC did not match the computed value.

### GREEN

- Regenerated the demo PNG with the repository Pillow install using
  `C:\Projects\FECreator\.venv\Scripts\python.exe`; the embedded bytes are now a deterministic
  1x1 opaque RGBA PNG (`image/png`) with valid IHDR, IDAT, and IEND CRCs.
- The regression now verifies signature, chunk bounds/order, CRC32 for every chunk, IEND, and full
  buffer consumption.
- Verification passed:

```text
npm run -w @laqieer/fecreator-web test -- src/demo/demoClient.test.ts -t "demo candidate artifacts are valid PNG bytes with matching chunk CRCs"
npm run -w @laqieer/fecreator-web test -- src/app/App.test.tsx src/app/AppRoot.test.tsx src/demo/demoClient.test.ts
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
```
