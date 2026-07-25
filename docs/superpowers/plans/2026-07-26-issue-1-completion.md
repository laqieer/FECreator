# Issue #1 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete GitHub issue #1 by making all portrait workflows,
review-gated publication, the local web workbench, ROM-free interoperability,
and the final v1 contract and CI surface fully operational.

**Architecture:** Preserve `FeCreatorApp` as the single facade and keep every
adapter thin. Add exact reference revision pinning and immutable candidate
records below the facade, split portrait workflow preparation into focused
modules, publish only approved candidates, and extend the existing React
composition boundary with app-backed local adapters and deterministic demo
adapters.

**Tech Stack:** Python 3.11-3.13, Pydantic v2, FastAPI, MCP SDK, NumPy,
OpenCV, Pillow at file boundaries, React 19, TypeScript 5.9, Vite 8, Vitest,
Testing Library, and Playwright.

## Global Constraints

- Keep the work inside portrait-focused v1; do not add ROM editing, hosted
  generation, other asset types, or other target specifications.
- Keep the server bound to `127.0.0.1` by default; do not add a public tunnel.
- Preserve immutable jobs, accepted sources, candidate artifacts, approvals,
  exports, reference revisions, and lineage.
- Resolve and persist an exact reference-pack revision at job creation; never
  use `latest()` while replaying or resuming a job.
- Missing capabilities, invalid states, unsafe paths, quality failures, and
  target validation failures must fail closed.
- Execute providers and external tools with argv lists and `shell=False`.
- Keep credentials, signed URLs, private art, and ROMs out of manifests,
  bundles, fixtures, logs, and the repository.
- Keep demo mode deterministic and offline: no fetch, WebSocket, upload,
  persistence, or filesystem calls.
- Use synthetic or original fixtures only.
- Build web assets before building the Python distribution.
- Do not create a GitHub Release.
- Use TDD for every behavior change.
- End each task with a focused commit, push it immediately, and monitor CI
  asynchronously while continuing independent work.

---

## Dependency order

1. Restore green baseline CI.
2. Finalize backend contracts and exact reference revision pinning.
3. Add candidate persistence and review lifecycle.
4. Implement the remaining portrait workflows.
5. Expose additive application and HTTP read/action surfaces.
6. Complete the React workbench and browser flows.
7. Add deterministic and optional external FEBuilder interoperability.
8. Freeze v1 contracts, finish packaging/docs/CI, and close issue #1.

### Task 1: Restore the green CI baseline with cross-platform path redaction

**Files:**
- Modify: `src/fecreator/core/redaction.py`
- Modify: `tests/core/test_redaction.py`
- Modify: `tests/interfaces/test_mcp_server.py`

**Interfaces:**
- Consumes: arbitrary diagnostic text containing POSIX, Windows, UNC, or
  mixed-separator absolute paths.
- Produces: `redact(text: str) -> str` that retains only the final basename
  for every recognized path shape.

- [ ] **Step 1: Add a failing mixed-separator unit test**

```python
def test_redact_mixed_posix_windows_path_keeps_only_basename(tmp_path: Path) -> None:
    text = f"build exploded at {tmp_path}\\nested\\artifact.png"

    redacted = redact(text)

    assert redacted == "build exploded at artifact.png"
    assert str(tmp_path) not in redacted
    assert "nested" not in redacted
```

Keep
`test_build_asset_returns_structured_redacted_mcp_error` unchanged so the
public MCP payload remains the regression test.

- [ ] **Step 2: Run the focused tests and confirm the Linux-shaped case fails**

Run:

```powershell
pytest -q tests/core/test_redaction.py tests/interfaces/test_mcp_server.py::test_build_asset_returns_structured_redacted_mcp_error
```

Expected: the new unit test fails because the result still includes the
temporary-directory basename and `nested`.

- [ ] **Step 3: Normalize mixed path basenames at the source**

```python
def _path_basename(value: str) -> str:
    posix_name = PurePosixPath(value).name
    return PureWindowsPath(posix_name).name


def _replace_windows_path(match: re.Match[str]) -> str:
    return _path_basename(match.group(0))


def _replace_posix_path(match: re.Match[str]) -> str:
    return _path_basename(match.group(0))
```

Do not weaken the existing secret patterns or sanitize only the MCP adapter;
all report and interface consumers must receive the same corrected behavior.

- [ ] **Step 4: Run the redaction and MCP suites**

Run:

```powershell
pytest -q tests/core/test_redaction.py tests/reporting/test_sanitize.py tests/interfaces/test_mcp_server.py
```

Expected: all selected tests pass on Windows, and the mixed-separator assertion
matches the current Linux CI failure.

- [ ] **Step 5: Commit, push, and start asynchronous CI monitoring**

```powershell
git add src/fecreator/core/redaction.py tests/core/test_redaction.py tests/interfaces/test_mcp_server.py
git commit -m "fix: redact mixed-platform paths consistently" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

Start `gh run watch` for the pushed SHA in a background shell and continue
Task 2 without waiting synchronously.

### Task 2: Pin exact reference-pack revisions in job manifests

**Files:**
- Modify: `src/fecreator/contracts/manifest.py`
- Modify: `src/fecreator/references/store.py`
- Modify: `src/fecreator/app.py`
- Modify: `src/fecreator/assets/portrait/plugin.py`
- Modify: `src/fecreator/contracts/schemas.py`
- Modify: `schemas/manifest.schema.json`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/types.contract.test.ts`
- Modify: `tests/contracts/test_manifest.py`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `tests/references/test_pack_store.py`
- Modify: `tests/app/test_app.py`

**Interfaces:**
- Produces: `Manifest.character_ref_pack_rev: int | None`.
- Produces:
  `ReferencePackStore.history(pack_id: str) -> list[ReferencePack]`.
- Changes: `FeCreatorApp.create_job()` persists a manifest whose reference
  revision is resolved exactly once.

- [ ] **Step 1: Write failing contract and replay tests**

```python
def test_reference_revision_requires_pack_id() -> None:
    with pytest.raises(ValidationError, match="character_ref_pack_rev"):
        Manifest.model_validate(
            {
                **manifest_payload(),
                "character_ref_pack_rev": 2,
            }
        )


def test_create_job_pins_latest_reference_revision(
    app: FeCreatorApp,
    data_root: Path,
) -> None:
    store = ReferencePackStore(data_root)
    store.create(reference_pack("hero", revision=1))
    store.new_revision("hero", traits={"hair": "red"})

    job = app.create_job(
        Manifest.model_validate(
            {
                **manifest_payload(),
                "character_ref_pack": "hero",
            }
        )
    )

    assert job.manifest.character_ref_pack_rev == 2


def test_pinned_job_ignores_later_reference_revision(
    app: FeCreatorApp,
    data_root: Path,
    tmp_path: Path,
) -> None:
    store = ReferencePackStore(data_root)
    store.create(reference_pack("hero", revision=1))
    job = app.create_job(
        Manifest.model_validate(
            {
                **manifest_payload(),
                "character_ref_pack": "hero",
            }
        )
    )
    store.new_revision("hero", traits={"hair": "blue"})

    plan = app.plan_sources(job.id, tmp_path / "plan")

    assert "blue" not in str(plan)
    assert app.get_job(job.id).manifest.character_ref_pack_rev == 1
```

Add a legacy persisted-job test that removes the revision from stored JSON and
expects an explicit `UnpinnedReferencePackError`.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```powershell
pytest -q tests/contracts/test_manifest.py tests/references/test_pack_store.py tests/app/test_app.py
```

Expected: failures for the missing manifest field, missing history API, and
current `latest()` replay behavior.

- [ ] **Step 3: Add the manifest field and exact store lookup**

```python
class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    asset_type: Literal["portrait"]
    target_spec: Literal["fe-gba-portrait-standard"]
    workflow: Literal[
        "text_to_portrait",
        "concept_to_portrait",
        "expression_refine",
        "masked_variant",
    ]
    provider: str
    character_ref_pack: str | None = None
    character_ref_pack_rev: int | None = Field(default=None, ge=1)
    sources: tuple[SourceSpec, ...] = ()
    edit: EditSpec | None = None
    params: Params = Field(default_factory=freeze_mapping)

    @model_validator(mode="after")
    def _validate_reference_revision(self) -> Manifest:
        if self.character_ref_pack_rev is not None and self.character_ref_pack is None:
            raise ValueError(
                "character_ref_pack_rev requires character_ref_pack"
            )
        return self
```

```python
class UnpinnedReferencePackError(ValueError):
    """Raised when a persisted job cannot replay an exact reference revision."""


def history(self, pack_id: str) -> list[ReferencePack]:
    normalized = self._normalize_pack_id(pack_id)
    with _path_lock(self._pack_dir(normalized), lock_path=self._lock_path(normalized)):
        return [
            self._read_pack_locked(normalized, revision)
            for revision in self._revision_numbers_locked(normalized)
        ]
```

Add an app helper:

```python
def _pin_reference_pack(self, manifest: Manifest) -> Manifest:
    if manifest.character_ref_pack is None:
        return manifest
    pack = (
        self._refs.latest(manifest.character_ref_pack)
        if manifest.character_ref_pack_rev is None
        else self._refs.get(
            manifest.character_ref_pack,
            manifest.character_ref_pack_rev,
        )
    )
    return manifest.model_copy(
        update={"character_ref_pack_rev": pack.revision}
    )
```

`create_job()` passes the pinned manifest to `JobService`. Both app and portrait
plugin reference loaders must require `character_ref_pack_rev` and call
`get()`.

- [ ] **Step 4: Regenerate schemas and update the TypeScript mirror**

```typescript
export interface Manifest {
  version: "1.0";
  asset_type: "portrait";
  target_spec: "fe-gba-portrait-standard";
  workflow:
    | "text_to_portrait"
    | "concept_to_portrait"
    | "expression_refine"
    | "masked_variant";
  provider: string;
  character_ref_pack?: string | null;
  character_ref_pack_rev?: number | null;
  sources: SourceSpec[];
  edit?: EditSpec | null;
  params: Record<string, string | number | boolean>;
}
```

Run:

```powershell
python -c "from pathlib import Path; from fecreator.contracts.schemas import export_schemas; export_schemas(Path('schemas'))"
pytest -q tests/contracts/test_manifest.py tests/contracts/test_schemas.py tests/references/test_pack_store.py tests/app/test_app.py
npm run -w @laqieer/fecreator-web test -- src/api/types.contract.test.ts
npm run -w @laqieer/fecreator-web typecheck
```

Expected: all selected Python and TypeScript checks pass.

- [ ] **Step 5: Commit and push**

```powershell
git add src/fecreator/contracts/manifest.py src/fecreator/references/store.py src/fecreator/app.py src/fecreator/assets/portrait/plugin.py src/fecreator/contracts/schemas.py schemas/manifest.schema.json web/src/api/types.ts web/src/api/types.contract.test.ts tests/contracts/test_manifest.py tests/contracts/test_schemas.py tests/references/test_pack_store.py tests/app/test_app.py
git commit -m "feat: pin reference-pack revisions in jobs" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 3: Add immutable candidate contracts, stores, and backend read models

**Files:**
- Create: `src/fecreator/contracts/review.py`
- Create: `src/fecreator/jobs/candidates.py`
- Modify: `src/fecreator/contracts/__init__.py`
- Modify: `src/fecreator/contracts/schemas.py`
- Modify: `src/fecreator/jobs/store.py`
- Modify: `src/fecreator/references/store.py`
- Modify: `src/fecreator/lineage/store.py`
- Modify: `src/fecreator/app.py`
- Create: `schemas/candidate.schema.json`
- Modify: `tests/contracts/test_schemas.py`
- Create: `tests/jobs/test_candidates.py`
- Modify: `tests/jobs/test_store.py`
- Modify: `tests/app/test_app.py`

**Interfaces:**
- Produces:
  `CandidateSnapshot(job_id, lineage_id, artifacts, diagnostics, metrics,
  created_at)`.
- Produces:
  `CandidateStore.create(snapshot) -> CandidateSnapshot` and
  `CandidateStore.load(job_id) -> CandidateSnapshot`.
- Produces deterministic app read methods for jobs, candidates, approvals,
  references, and lineage.

- [ ] **Step 1: Write failing candidate immutability and ordering tests**

```python
def test_candidate_store_create_is_immutable(data_root: Path) -> None:
    store = CandidateStore(data_root)
    snapshot = candidate_snapshot(job_id="job-1")

    assert store.create(snapshot) == snapshot
    with pytest.raises(FileExistsError):
        store.create(snapshot)
    assert store.load("job-1") == snapshot


def test_app_read_collections_are_deterministic(app: FeCreatorApp) -> None:
    first = app.create_job(manifest())
    second = app.create_job(manifest())

    assert [job.id for job in app.list_jobs()] == sorted([first.id, second.id])
```

Add tests for reference history revision order and lineage ancestor/child order.

- [ ] **Step 2: Run the focused store tests and confirm they fail**

Run:

```powershell
pytest -q tests/jobs/test_candidates.py tests/jobs/test_store.py tests/references/test_pack_store.py tests/lineage/test_lineage_store.py tests/app/test_app.py
```

Expected: import and missing-method failures.

- [ ] **Step 3: Define the frozen candidate contract**

```python
class CandidateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["1.0"] = "1.0"
    job_id: str
    lineage_id: str
    artifacts: tuple[Artifact, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    metrics: Mapping[str, float] = Field(default_factory=freeze_mapping)
    created_at: str

    @field_validator("metrics", mode="after")
    @classmethod
    def _freeze_metrics(
        cls, value: Mapping[str, float]
    ) -> Mapping[str, float]:
        return freeze_mapping(value)
```

Implement `CandidateStore` at
`jobs/<job_id>/candidate/candidate.json` with `safe_join()`, the job lock, and
`write_json_atomic()`. It must reject a second create and validate loaded JSON.
Initialize one `CandidateStore` and one `LineageStore` in `FeCreatorApp.__init__`
so facade read methods reuse the configured data root.

- [ ] **Step 4: Add deterministic store and app read methods**

```python
def list_jobs(self) -> list[Job]:
    return self._jobs.list()


def get_job_candidate(self, job_id: str) -> CandidateSnapshot:
    return self._candidates.load(job_id)


def list_approval_decisions(self, job_id: str) -> list[ApprovalRecord]:
    return self._approvals.decisions(job_id)


def get_reference_pack(self, pack_id: str, revision: int) -> ReferencePack:
    return self._refs.get(pack_id, revision)


def list_reference_history(self, pack_id: str) -> list[ReferencePack]:
    return self._refs.history(pack_id)


def get_lineage(self, asset_id: str) -> LineageNode:
    return self._lineage.get(asset_id)
```

Add corresponding ancestor and child methods. `JobStore.list()` validates every
visible job file and sorts by job ID; it must not silently skip corruption.

- [ ] **Step 5: Export the candidate schema, run tests, commit, and push**

Run:

```powershell
python -c "from pathlib import Path; from fecreator.contracts.schemas import export_schemas; export_schemas(Path('schemas'))"
pytest -q tests/jobs/test_candidates.py tests/jobs/test_store.py tests/references/test_pack_store.py tests/lineage/test_lineage_store.py tests/app/test_app.py tests/contracts/test_schemas.py
```

Then:

```powershell
git add src/fecreator/contracts/review.py src/fecreator/jobs/candidates.py src/fecreator/contracts/__init__.py src/fecreator/contracts/schemas.py src/fecreator/jobs/store.py src/fecreator/references/store.py src/fecreator/lineage/store.py src/fecreator/app.py schemas/candidate.schema.json tests/contracts/test_schemas.py tests/jobs/test_candidates.py tests/jobs/test_store.py tests/app/test_app.py
git commit -m "feat: persist immutable review candidates" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 4: Build text and concept workflows into immutable candidates

**Files:**
- Create: `src/fecreator/assets/portrait/workflows.py`
- Create: `src/fecreator/assets/portrait/candidate.py`
- Modify: `src/fecreator/assets/portrait/plugin.py`
- Modify: `src/fecreator/assets/portrait/prompt_plan.py`
- Modify: `src/fecreator/assets/portrait/references.py`
- Modify: `tests/portrait/test_prompt_plan.py`
- Create: `tests/portrait/test_workflows.py`
- Modify: `tests/portrait/test_build_e2e.py`

**Interfaces:**
- Produces internal `PreparedPortrait`.
- Produces:
  `prepare_text_to_portrait(manifest, pack, provider, workspace) ->
  PreparedPortrait` and
  `prepare_concept_to_portrait(manifest, pack, provider, workspace) ->
  PreparedPortrait`.
- Changes `PortraitPlugin.build()` to create one candidate and transition to
  `waiting_for_review`; it no longer publishes the final package.
- Produces
  `assemble_candidate_sheet(main_rgb, bg_rgb) -> NDArray[np.uint8]`,
  `export_candidate_package(package_dir, sheet_rgb, bg_rgb) -> Path`,
  `candidate_artifacts(workspace, package_dir) -> tuple[Artifact, ...]`,
  `candidate_lineage(...) -> LineageNode`, and
  `publish_candidate_atomically(workspace, snapshot, lineage) -> None`.

- [ ] **Step 1: Write failing text and concept candidate tests**

```python
def test_text_build_stops_for_review(app: FeCreatorApp) -> None:
    job = app.create_job(text_manifest())

    result = app.build(job.id)

    assert result.ok is True
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW
    assert app.get_job_candidate(job.id).lineage_id == f"{job.id}-candidate"
    assert not (job_workspace(job.id) / "package").exists()


def test_concept_workflow_requires_concept_input(app: FeCreatorApp) -> None:
    job = app.create_job(concept_manifest(sources=()))

    result = app.build(job.id)

    assert result.ok is False
    assert any(d.code == "WORKFLOW_INPUT_MISSING" for d in result.diagnostics)
```

Add a successful concept test that verifies `IMAGE_TO_IMAGE` capability and
concept references in the provider request.

- [ ] **Step 2: Run the focused portrait tests and confirm they fail**

Run:

```powershell
pytest -q tests/portrait/test_prompt_plan.py tests/portrait/test_workflows.py tests/portrait/test_build_e2e.py
```

Expected: text still completes directly and concept raises
`NotImplementedError`.

- [ ] **Step 3: Add focused workflow preparation types**

```python
@dataclass(frozen=True)
class PreparedPortrait:
    sheet_rgb: NDArray[np.uint8]
    operation: Operation
    provider_model: str | None
    prompt: str | None
    seed: int | None
    diagnostics: tuple[Diagnostic, ...]
    parents: tuple[str, ...] = ()
    mask: str | None = None
    protected_regions: tuple[Region, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)


def prepare_text_to_portrait(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    require_capabilities(provider, {Capability.TEXT_TO_IMAGE})
    plan = prompt_plan.build_prompt_plan(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=plan.neutral_prompt,
            references=concept_art_artifacts(pack) if pack else (),
            params=manifest.params,
        ),
        workspace,
    )
    artifact = require_single_image_artifact(response, role="neutral")
    neutral = load_rgb(safe_provider_artifact(workspace, artifact.path))
    return PreparedPortrait(
        sheet_rgb=assemble_candidate_sheet(
            align_to_main(neutral, GREEN_BG),
            GREEN_BG,
        ),
        operation=Operation.CREATE_NEUTRAL,
        provider_model=response.model,
        prompt=plan.neutral_prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
    )


def prepare_concept_to_portrait(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    references = concept_inputs(manifest, pack, workspace)
    if not references:
        raise WorkflowInputError(
            "concept_to_portrait requires submitted or reference-pack concept art"
        )
    require_capabilities(provider, {Capability.IMAGE_TO_IMAGE})
    plan = prompt_plan.build_prompt_plan(manifest, pack)
    response = provider.generate(
        GenRequest(
            workflow=manifest.workflow,
            prompt=plan.neutral_prompt,
            references=references,
            params=manifest.params,
        ),
        workspace,
    )
    artifact = require_single_image_artifact(response, role="neutral")
    neutral = load_rgb(safe_provider_artifact(workspace, artifact.path))
    return PreparedPortrait(
        sheet_rgb=assemble_candidate_sheet(
            align_to_main(neutral, GREEN_BG),
            GREEN_BG,
        ),
        operation=Operation.IMPORT_CONCEPT,
        provider_model=response.model,
        prompt=plan.neutral_prompt,
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
    )
```

Implement the bodies with existing prompt planning, capability refusal,
provider artifact containment, image budgets, and `align_to_main()`. Concept
preparation must require submitted concept art or pinned-pack concept artifacts.
For non-text `SourceSpec` values, `ref` is a normalized filename beneath the
job's immutable `submitted/` directory; it is never treated as an arbitrary
filesystem path.

- [ ] **Step 4: Persist candidate package and candidate lineage atomically**

`candidate.py` owns:

```python
def publish_candidate(
    *,
    ctx: PipelineContext,
    manifest: Manifest,
    prepared: PreparedPortrait,
    reference_pack: ReferencePack | None,
) -> CandidateSnapshot:
    candidate_root = safe_join(ctx.workspace, "candidate")
    package_dir = safe_join(candidate_root, "package")
    export_candidate_package(package_dir, prepared.sheet_rgb, GREEN_BG)
    diagnostics = tuple(FeGbaPortraitStandard().validate(package_dir))
    if has_errors(diagnostics):
        raise CandidateValidationError(diagnostics)
    artifacts = candidate_artifacts(ctx.workspace, package_dir)
    lineage = candidate_lineage(
        job_id=ctx.job_id,
        manifest=manifest,
        prepared=prepared,
        reference_pack=reference_pack,
        artifacts=artifacts,
    )
    snapshot = CandidateSnapshot(
        job_id=ctx.job_id,
        lineage_id=lineage.asset_id,
        artifacts=artifacts,
        diagnostics=prepared.diagnostics + diagnostics,
        metrics=prepared.metrics,
        created_at=lineage.created_at,
    )
    publish_candidate_atomically(ctx.workspace, snapshot, lineage)
    return snapshot
```

It writes only:

```text
jobs/<job_id>/candidate/package/hero.png
jobs/<job_id>/candidate/package/hero.pal
jobs/<job_id>/candidate/candidate.json
```

Validate the candidate package before visibility, add the workflow lineage node,
and roll back both candidate files and lineage if the job transition to
`waiting_for_review` fails.

- [ ] **Step 5: Run portrait tests, commit, and push**

Run:

```powershell
pytest -q tests/portrait/test_prompt_plan.py tests/portrait/test_workflows.py tests/portrait/test_build_e2e.py tests/jobs/test_candidates.py
```

Then:

```powershell
git add src/fecreator/assets/portrait/workflows.py src/fecreator/assets/portrait/candidate.py src/fecreator/assets/portrait/plugin.py src/fecreator/assets/portrait/prompt_plan.py src/fecreator/assets/portrait/references.py tests/portrait/test_prompt_plan.py tests/portrait/test_workflows.py tests/portrait/test_build_e2e.py
git commit -m "feat: build text and concept review candidates" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 5: Implement expression-refine and masked-variant candidates

**Files:**
- Modify: `src/fecreator/assets/portrait/workflows.py`
- Modify: `src/fecreator/assets/portrait/expressions.py`
- Modify: `src/fecreator/assets/portrait/variants.py`
- Modify: `src/fecreator/specs/fire_emblem/gba/portrait_standard/assembly.py`
- Modify: `tests/portrait/test_workflows.py`
- Modify: `tests/portrait/test_expressions.py`
- Modify: `tests/portrait/test_variants.py`
- Modify: `tests/portrait/test_build_e2e.py`

**Interfaces:**
- Produces:
  `prepare_expression_refine(manifest, pack, provider, workspace) ->
  PreparedPortrait`.
- Produces:
  `prepare_masked_variant(manifest, pack, provider, workspace) ->
  PreparedPortrait`.
- Consumes only submitted, workspace-contained approved portraits and masks.

- [ ] **Step 1: Write failing workflow input and invariance tests**

```python
def test_expression_refine_preserves_patch_borders(app: FeCreatorApp) -> None:
    job = create_expression_job_with_submitted_base(app)

    result = app.build(job.id)
    sheet = load_indexed(candidate_package(job.id) / "hero.png")

    assert result.ok is True
    assert_expression_borders_match_base(sheet)


def test_masked_variant_changes_only_mask_and_preserves_regions(
    app: FeCreatorApp,
) -> None:
    job = create_masked_job_with_sources(app)

    result = app.build(job.id)

    assert result.ok is True
    assert not any(
        diagnostic.code == "PROTECTED_REGION_CHANGED"
        for diagnostic in result.diagnostics
    )
```

Add negative tests for absent approved portrait, absent mask, malformed mask,
shape mismatch, provider capability refusal, and protected-region change.
An `approved_portrait` source names the submitted indexed PNG; the matching
same-basename JASC palette is required. `EditSpec.mask_path` is likewise a
normalized filename beneath `submitted/`.

- [ ] **Step 2: Run the focused tests and confirm the workflows fail**

Run:

```powershell
pytest -q tests/portrait/test_expressions.py tests/portrait/test_variants.py tests/portrait/test_workflows.py tests/portrait/test_build_e2e.py
```

Expected: both workflows still raise `NotImplementedError`.

- [ ] **Step 3: Implement expression preparation**

```python
def prepare_expression_refine(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    base_sheet = load_approved_sheet(workspace, manifest)
    require_capabilities(provider, {Capability.IMAGE_TO_IMAGE})
    response = request_expression_cells(provider, manifest, pack, workspace)
    refined_sheet = assemble_refined_expressions(
        base_sheet,
        response,
        workspace,
    )
    return PreparedPortrait(
        sheet_rgb=refined_sheet,
        operation=Operation.REFINE_EXPRESSION,
        provider_model=response.model,
        prompt=expression_prompt(manifest, pack),
        seed=response.seed,
        diagnostics=tuple(response.diagnostics),
        parents=approved_portrait_parents(manifest),
    )
```

The assembly helper must retain each base cell's one-pixel border and require
all configured expression roles.

- [ ] **Step 4: Implement masked-variant preparation**

```python
def prepare_masked_variant(
    manifest: Manifest,
    pack: ReferencePack | None,
    provider: Provider,
    workspace: Path,
) -> PreparedPortrait:
    base_sheet = load_approved_sheet(workspace, manifest)
    base_main = extract_main_portrait(base_sheet)
    mask = load_bool_mask(workspace, manifest.edit)
    require_capabilities(provider, {Capability.MASKED_EDIT})
    response = request_masked_edit(
        provider,
        manifest,
        pack,
        base_main,
        mask,
        workspace,
    )
    edited = load_single_image_artifact(response, workspace)
    result, diagnostics = build_variant(
        base_main,
        edited,
        mask,
        manifest.edit.protected_regions,
    )
    return PreparedPortrait(
        sheet_rgb=replace_main_portrait(base_sheet, result),
        operation=Operation.VARIANT_MASKED_EDIT,
        provider_model=response.model,
        prompt=masked_prompt(manifest, pack),
        seed=response.seed,
        diagnostics=tuple(response.diagnostics) + tuple(diagnostics),
        parents=approved_portrait_parents(manifest),
        mask=manifest.edit.mask_path,
        protected_regions=manifest.edit.protected_regions,
    )
```

Any protected-region error prevents candidate publication.

- [ ] **Step 5: Run all portrait tests, commit, and push**

Run:

```powershell
pytest -q tests/portrait
```

Then:

```powershell
git add src/fecreator/assets/portrait/workflows.py src/fecreator/assets/portrait/expressions.py src/fecreator/assets/portrait/variants.py src/fecreator/specs/fire_emblem/gba/portrait_standard/assembly.py tests/portrait/test_workflows.py tests/portrait/test_expressions.py tests/portrait/test_variants.py tests/portrait/test_build_e2e.py
git commit -m "feat: add expression and masked portrait workflows" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 6: Gate final publication on approval and support rejection and retry

**Files:**
- Create: `src/fecreator/assets/portrait/publication.py`
- Modify: `src/fecreator/jobs/model.py`
- Modify: `src/fecreator/jobs/store.py`
- Modify: `src/fecreator/jobs/service.py`
- Modify: `src/fecreator/jobs/approvals.py`
- Modify: `src/fecreator/app.py`
- Modify: `src/fecreator/assets/portrait/plugin.py`
- Modify: `src/fecreator/reporting/json_report.py`
- Modify: `src/fecreator/reporting/bundle.py`
- Modify: `tests/jobs/test_model.py`
- Modify: `tests/jobs/test_service.py`
- Modify: `tests/jobs/test_approvals.py`
- Modify: `tests/app/test_app.py`
- Modify: `tests/portrait/test_build_e2e.py`
- Modify: `tests/reporting/test_json_report.py`
- Modify: `tests/reporting/test_bundle.py`

**Interfaces:**
- Adds `Job.parent_candidate_id: str | None`.
- Produces `approve_review()`, `reject_review()`, `finalize_job()`, and
  `retry_job()` on `FeCreatorApp`.
- Final export lineage ID is `<job_id>-export`; its parent is
  `<job_id>-candidate`.
- Produces
  `publish_final_artifacts_atomically(data_root, job, candidate, approval,
  diagnostics) -> JobResult`.

- [ ] **Step 1: Write failing review lifecycle tests**

```python
def test_finalize_requires_candidate_approval(app: FeCreatorApp) -> None:
    job = build_candidate(app)

    result = app.finalize_job(job.id)

    assert result.ok is False
    assert any(d.code == "APPROVAL_MISSING" for d in result.diagnostics)
    assert app.get_job(job.id).state is JobState.WAITING_FOR_REVIEW


def test_reject_preserves_candidate_and_fails_job(app: FeCreatorApp) -> None:
    job = build_candidate(app)

    record = app.reject_review(job.id, actor="reviewer", reason="bad silhouette")

    assert record.decision == "rejected"
    assert app.get_job(job.id).state is JobState.FAILED
    assert app.get_job_candidate(job.id).job_id == job.id


def test_retry_creates_linked_immutable_job(app: FeCreatorApp) -> None:
    rejected = reject_candidate(app)

    retry = app.retry_job(rejected.id, actor="reviewer")

    assert retry.id != rejected.id
    assert retry.parent_candidate_id == f"{rejected.id}-candidate"
    assert retry.state is JobState.CREATED
```

Add success and rollback tests for final package/report/bundle/export lineage.

- [ ] **Step 2: Run lifecycle tests and confirm they fail**

Run:

```powershell
pytest -q tests/jobs/test_model.py tests/jobs/test_service.py tests/jobs/test_approvals.py tests/app/test_app.py tests/portrait/test_build_e2e.py tests/reporting/test_json_report.py tests/reporting/test_bundle.py
```

Expected: missing methods and direct-publication assumptions fail.

- [ ] **Step 3: Add parent linkage and specialized review methods**

```python
class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    state: JobState
    manifest: Manifest
    parent_candidate_id: str | None = None
    revision: int = Field(ge=1)
    created_at: str
    updated_at: str
```

```python
def approve_review(self, job_id: str, actor: str) -> ApprovalRecord:
    job = self._require_state(job_id, JobState.WAITING_FOR_REVIEW)
    return self._approvals.approve(job.id, "candidate", actor)


def reject_review(self, job_id: str, actor: str, reason: str) -> ApprovalRecord:
    job = self._require_state(job_id, JobState.WAITING_FOR_REVIEW)
    record: ApprovalRecord | None = None

    def publish_rejection(_candidate_job: Job) -> None:
        nonlocal record
        record = self._approvals.reject(job.id, "candidate", actor, reason)

    def rollback_rejection() -> None:
        if record is not None:
            self._approvals.discard_pending(record)

    self._service.transition(
        job.id,
        JobState.FAILED,
        before_persist=publish_rejection,
        rollback=rollback_rejection,
    )
    if record is None:
        raise RuntimeError("rejection transition completed without an approval record")
    return record


def retry_job(self, job_id: str, actor: str) -> Job:
    rejected = self._require_state(job_id, JobState.FAILED)
    self._require_rejected_candidate(rejected.id)
    return self._service.create_job(
        rejected.manifest,
        parent_candidate_id=f"{rejected.id}-candidate",
    )
```

Record review and retry events with actor but no secret-bearing free-form data.
`ApprovalStore.discard_pending(record)` may remove only the exact last record
written by the same transition while holding the approval-file lock; it must
refuse to delete any earlier visible decision.

- [ ] **Step 4: Add approval-gated atomic finalization**

`publication.py` exposes:

```python
def finalize_candidate(
    *,
    data_root: Path,
    job: Job,
    candidate: CandidateSnapshot,
    approval: ApprovalRecord,
) -> JobResult:
    if approval.stage != "candidate" or approval.decision != "approved":
        return JobResult(
            job_id=job.id,
            ok=False,
            diagnostics=(error("APPROVAL_MISSING", "candidate is not approved"),),
        )
    candidate_package = safe_join(
        data_root,
        "jobs",
        job.id,
        "candidate",
        "package",
    )
    diagnostics = tuple(FeGbaPortraitStandard().validate(candidate_package))
    if has_errors(diagnostics):
        return JobResult(job_id=job.id, ok=False, diagnostics=diagnostics)
    return publish_final_artifacts_atomically(
        data_root=data_root,
        job=job,
        candidate=candidate,
        approval=approval,
        diagnostics=diagnostics,
    )
```

It revalidates `candidate/package`, stages the public `package`, report, bundle,
and export lineage, then uses the existing transition publish/rollback hooks for
`waiting_for_review -> validating -> completed`. On failure it removes only
new public artifacts and the export lineage node, preserves `candidate/`, and
returns the job to `waiting_for_review`.

- [ ] **Step 5: Run lifecycle suites, commit, and push**

Run:

```powershell
pytest -q tests/jobs tests/app/test_app.py tests/portrait/test_build_e2e.py tests/reporting tests/lineage/test_lineage_store.py
```

Then:

```powershell
git add src/fecreator/assets/portrait/publication.py src/fecreator/jobs/model.py src/fecreator/jobs/store.py src/fecreator/jobs/service.py src/fecreator/jobs/approvals.py src/fecreator/app.py src/fecreator/assets/portrait/plugin.py src/fecreator/reporting/json_report.py src/fecreator/reporting/bundle.py tests/jobs tests/app/test_app.py tests/portrait/test_build_e2e.py tests/reporting
git commit -m "feat: require review before portrait publication" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 7: Expose additive CLI, HTTP, MCP, and WebSocket operations

**Files:**
- Modify: `src/fecreator/interfaces/cli_json.py`
- Modify: `src/fecreator/interfaces/http_api.py`
- Modify: `src/fecreator/interfaces/mcp_server.py`
- Modify: `src/fecreator/interfaces/websocket.py`
- Modify: `pyproject.toml`
- Modify: `docs/interfaces.md`
- Modify: `tests/interfaces/test_cli_json.py`
- Modify: `tests/interfaces/test_http_api.py`
- Modify: `tests/interfaces/test_mcp_server.py`
- Modify: `tests/interfaces/test_websocket.py`
- Modify: `tests/integration/test_interface_equivalence.py`
- Modify: `tests/integration/test_no_bypass.py`

**Interfaces:**
- Adds read operations for jobs, candidates, approvals, references, and lineage.
- Adds review, finalize, retry, and cancel actions.
- Removes or renames no existing command, route, or MCP tool.
- Adds facade methods:
  `plan_job_sources(job_id) -> SourcePlan`,
  `validate_job(job_id) -> list[Diagnostic]`,
  `list_reference_packs() -> list[str]`,
  `get_job_report(job_id) -> JsonObject`,
  `list_bundle_entries(job_id) -> list[BundleEntry]`,
  `read_job_artifact(job_id, relative_path) -> bytes`, and
  `read_bundle_file(job_id, relative_path) -> bytes`.

- [ ] **Step 1: Write failing adapter-equivalence tests**

```python
@pytest.mark.parametrize("surface", ["app", "cli", "http", "mcp"])
def test_candidate_approval_and_finalize_are_equivalent(surface: str) -> None:
    result = run_review_flow(surface)

    assert result["job"]["state"] == "completed"
    assert result["approval"]["decision"] == "approved"
    assert result["result"]["lineage_id"].endswith("-export")
```

Add exact-shape tests for:

```text
GET /api/jobs
GET /api/jobs/{job_id}/candidate
GET /api/jobs/{job_id}/approvals
POST /api/jobs/{job_id}/plan-sources
POST /api/jobs/{job_id}/sources
POST /api/jobs/{job_id}/validate
GET /api/jobs/{job_id}/artifacts/{path}
GET /api/jobs/{job_id}/report
GET /api/jobs/{job_id}/bundle
GET /api/jobs/{job_id}/bundle/{path}
GET /api/references
GET /api/references/{pack_id}/history
GET /api/lineage/{asset_id}
GET /api/lineage/{asset_id}/ancestors
GET /api/lineage/{asset_id}/children
POST /api/jobs/{job_id}/approve
POST /api/jobs/{job_id}/reject
POST /api/jobs/{job_id}/finalize
POST /api/jobs/{job_id}/retry
POST /api/jobs/{job_id}/cancel
```

- [ ] **Step 2: Run interface tests and confirm missing operations**

Run:

```powershell
pytest -q tests/interfaces tests/integration/test_interface_equivalence.py tests/integration/test_no_bypass.py
```

Expected: route/tool/command lookup failures for the additive surface.

- [ ] **Step 3: Add typed HTTP request models and routes**

```python
class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor: str


class RejectRequest(ReviewRequest):
    reason: str
```

Route bodies call only `FeCreatorApp`; normalize every storage ID and map
expected failures to structured diagnostics. Add
`python-multipart>=0.0.20,<1` for bounded multipart source uploads. Stream each
upload into a uniquely named temporary directory with normalized filenames and
an explicit byte budget, then pass that directory to `app.submit_sources()`.
Artifact and bundle reads must use `safe_join()` beneath the selected job
workspace and return only regular files.

- [ ] **Step 4: Add matching CLI and MCP handlers**

Keep existing JSON envelope and `CallToolResult` helpers. Add tool names and
commands for candidate inspection, approval decisions, finalization, retry,
reference history, and lineage queries. New review events flow through the
existing persisted-event WebSocket snapshot without a second event source.

- [ ] **Step 5: Run interface suites, commit, and push**

Run:

```powershell
pytest -q tests/interfaces tests/integration/test_interface_equivalence.py tests/integration/test_no_bypass.py
```

Then:

```powershell
git add src/fecreator/interfaces/cli_json.py src/fecreator/interfaces/http_api.py src/fecreator/interfaces/mcp_server.py src/fecreator/interfaces/websocket.py pyproject.toml docs/interfaces.md tests/interfaces tests/integration/test_interface_equivalence.py tests/integration/test_no_bypass.py
git commit -m "feat: expose review lifecycle across interfaces" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 8: Expand web API contracts and deterministic demo adapters

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/client.test.ts`
- Modify: `web/src/api/types.contract.test.ts`
- Modify: `web/src/demo/fixtures.ts`
- Modify: `web/src/demo/demoClient.ts`
- Modify: `web/src/demo/demoClient.test.ts`
- Modify: `web/src/app/composition.test.ts`
- Modify: `web/src/test/util.tsx`

**Interfaces:**
- Produces a complete `ApiClient` for jobs, candidates, reviews, references,
  lineage, validation, reports, and bundles.
- Demo methods have the same signatures and mutate only deterministic
  in-memory fixtures.

- [ ] **Step 1: Write failing client and demo parity tests**

```typescript
it("uses the review and history endpoints", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse([jobFixture]))
    .mockResolvedValueOnce(jsonResponse(candidateFixture))
    .mockResolvedValueOnce(jsonResponse(approvalFixture));
  const client = createHttpApiClient(fetchMock);

  await expect(client.listJobs()).resolves.toEqual([jobFixture]);
  await expect(client.getJobCandidate(jobFixture.id)).resolves.toEqual(
    candidateFixture,
  );
  await expect(
    client.approveReview(jobFixture.id, "reviewer"),
  ).resolves.toEqual(approvalFixture);

  expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/jobs", expect.any(Object));
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    `/api/jobs/${jobFixture.id}/candidate`,
    expect.any(Object),
  );
});
```

Add a demo test that invokes every new method while global `fetch` and
`WebSocket` throw if called.

- [ ] **Step 2: Run the web contract tests and confirm missing methods**

Run:

```powershell
npm run -w @laqieer/fecreator-web test -- src/api/client.test.ts src/api/types.contract.test.ts src/demo/demoClient.test.ts src/app/composition.test.ts
```

Expected: TypeScript compilation or runtime failures for the missing methods.

- [ ] **Step 3: Add exact TypeScript read models**

```typescript
export interface CandidateSnapshot {
  version: "1.0";
  job_id: string;
  lineage_id: string;
  artifacts: Artifact[];
  diagnostics: Diagnostic[];
  metrics: Record<string, number>;
  created_at: string;
}

export interface ApprovalRecord {
  job_id: string;
  stage: string;
  decision: "approved" | "rejected";
  actor: string;
  reason?: string | null;
  at: string;
}

export interface BundleEntry {
  path: string;
  sha256: string;
  media_type: string;
  size: number;
}
```

Mirror the final Python job and manifest fields exactly, including
`parent_candidate_id` and `character_ref_pack_rev`.

- [ ] **Step 4: Implement local and demo clients**

```typescript
export interface ApiClient {
  listAssets(): Promise<string[]>;
  listSpecs(): Promise<string[]>;
  listProviders(): Promise<string[]>;
  listJobs(): Promise<Job[]>;
  createJob(manifest: Manifest): Promise<Job>;
  getJob(jobId: string): Promise<Job>;
  planSources(jobId: string): Promise<SourcePlan>;
  submitSources(jobId: string, files: File[]): Promise<Job>;
  getJobCandidate(jobId: string): Promise<CandidateSnapshot>;
  listApprovals(jobId: string): Promise<ApprovalRecord[]>;
  approveReview(jobId: string, actor: string): Promise<ApprovalRecord>;
  rejectReview(
    jobId: string,
    actor: string,
    reason: string,
  ): Promise<ApprovalRecord>;
  finalizeJob(jobId: string): Promise<JobResult>;
  retryJob(jobId: string, actor: string): Promise<Job>;
  cancelJob(jobId: string): Promise<Job>;
  listReferencePacks(): Promise<string[]>;
  listReferenceHistory(packId: string): Promise<ReferencePack[]>;
  getLineage(assetId: string): Promise<LineageNode>;
  getLineageAncestors(assetId: string): Promise<LineageNode[]>;
  getLineageChildren(assetId: string): Promise<LineageNode[]>;
  validateJob(jobId: string): Promise<Diagnostic[]>;
  getArtifact(jobId: string, path: string): Promise<Blob>;
  getJobReport(jobId: string): Promise<Report>;
  listBundleEntries(jobId: string): Promise<BundleEntry[]>;
  getBundleFile(jobId: string, path: string): Promise<Blob>;
}
```

The demo implementation clones fixtures before returning them and applies
review state changes deterministically.

- [ ] **Step 5: Run tests, commit, and push**

Run:

```powershell
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web test -- src/api/client.test.ts src/api/types.contract.test.ts src/demo/demoClient.test.ts src/app/composition.test.ts
```

Then:

```powershell
git add web/src/api/types.ts web/src/api/client.ts web/src/api/client.test.ts web/src/api/types.contract.test.ts web/src/demo/fixtures.ts web/src/demo/demoClient.ts web/src/demo/demoClient.test.ts web/src/app/composition.test.ts web/src/test/util.tsx
git commit -m "feat(web): expand workbench API contracts" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 9: Add the live job dashboard and manifest controls

**Files:**
- Create: `web/src/dashboard/JobQueue.tsx`
- Create: `web/src/dashboard/JobQueue.test.tsx`
- Create: `web/src/controls/ManifestControls.tsx`
- Create: `web/src/controls/ManifestControls.test.tsx`
- Create: `web/src/controls/SourceStatus.tsx`
- Create: `web/src/controls/SourceStatus.test.tsx`
- Create: `web/src/workbench/useWorkbench.ts`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/App.test.tsx`
- Create: `web/src/app/App.workbench.test.tsx`

**Interfaces:**
- `useWorkbench(api, events)` owns selected job, refresh, mutation state, and
  error display.
- `ManifestControls` emits a fully validated `Manifest` value and never reads
  global configuration.

- [ ] **Step 1: Write failing dashboard and manifest tests**

```tsx
it("selects a persisted job from the queue", async () => {
  const api = apiFixture({ jobs: [createdJob, reviewJob] });
  renderWorkbench({ api });

  await userEvent.click(await screen.findByRole("button", {
    name: /review job/i,
  }));

  expect(screen.getByText(reviewJob.id)).toBeInTheDocument();
  expect(api.getJobCandidate).toHaveBeenCalledWith(reviewJob.id);
});

it("submits the selected workflow and pinned reference revision", async () => {
  const onSubmit = vi.fn();
  render(<ManifestControls {...manifestProps} onSubmit={onSubmit} />);

  await userEvent.selectOptions(
    screen.getByLabelText(/workflow/i),
    "masked_variant",
  );
  await userEvent.click(screen.getByRole("button", { name: /create job/i }));

  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({ workflow: "masked_variant" }),
  );
});
```

- [ ] **Step 2: Run the focused component tests**

Run:

```powershell
npm run -w @laqieer/fecreator-web test -- src/app/App.test.tsx src/app/App.workbench.test.tsx src/dashboard/JobQueue.test.tsx src/controls/ManifestControls.test.tsx src/controls/SourceStatus.test.tsx
```

Expected: missing component and hook failures.

- [ ] **Step 3: Implement the workbench hook**

```typescript
export function useWorkbench(api: ApiClient, events: JobEventSource) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshJobs = useCallback(async () => {
    try {
      const next = await api.listJobs();
      setJobs(next);
      setSelectedJobId((current) => current ?? next[0]?.id ?? null);
      setError(null);
    } catch (cause) {
      setError(toErrorMessage(cause));
    }
  }, [api]);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  return {
    jobs,
    selectedJobId,
    selectJob: setSelectedJobId,
    refreshJobs,
    error,
    events,
  };
}
```

Keep mutation helpers in the hook so components remain presentational.

- [ ] **Step 4: Replace hardcoded shell data with live controls**

`App.tsx` composes `JobQueue`, `ManifestControls`, `SourceStatus`, and the
existing timeline/review tabs from `useWorkbench()`. Every loading and error
state uses the existing accessible status patterns.

- [ ] **Step 5: Run tests, commit, and push**

Run:

```powershell
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web test -- src/app src/dashboard src/controls
```

Then:

```powershell
git add web/src/dashboard web/src/controls web/src/workbench/useWorkbench.ts web/src/app/App.tsx web/src/app/App.test.tsx web/src/app/App.workbench.test.tsx
git commit -m "feat(web): add job dashboard and manifest controls" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 10: Wire review, mask, validation, lineage, report, and bundle panels

**Files:**
- Modify: `web/src/review/ReviewGallery.tsx`
- Modify: `web/src/review/ReviewGallery.test.tsx`
- Modify: `web/src/canvas/MaskEditor.tsx`
- Modify: `web/src/canvas/MaskEditor.test.tsx`
- Modify: `web/src/palette/PalettePreview.tsx`
- Modify: `web/src/palette/PalettePreview.test.tsx`
- Modify: `web/src/lineage/LineageView.tsx`
- Modify: `web/src/lineage/LineageView.test.tsx`
- Modify: `web/src/references/ReferenceBoard.tsx`
- Modify: `web/src/references/ReferenceBoard.test.tsx`
- Create: `web/src/validation/ValidationPanel.tsx`
- Create: `web/src/validation/ValidationPanel.test.tsx`
- Create: `web/src/reports/ReportBundlePanel.tsx`
- Create: `web/src/reports/ReportBundlePanel.test.tsx`
- Modify: `web/src/app/App.tsx`

**Interfaces:**
- Review buttons invoke persisted approve/reject/finalize/retry methods.
- Mask edits emit `EditSpec` values with protected regions.
- Lineage and references use backend history, not static fixtures in local mode.

- [ ] **Step 1: Write failing live-action tests**

```tsx
it("approves and finalizes the selected candidate", async () => {
  const api = apiFixture({ candidate: candidateFixture });
  renderWorkbench({ api, selectedJob: reviewJob });

  await userEvent.click(screen.getByRole("button", { name: /approve/i }));
  await userEvent.click(screen.getByRole("button", { name: /finalize/i }));

  expect(api.approveReview).toHaveBeenCalledWith(reviewJob.id, "local-user");
  expect(api.finalizeJob).toHaveBeenCalledWith(reviewJob.id);
});

it("rejects with a required reason", async () => {
  const api = apiFixture({ candidate: candidateFixture });
  renderWorkbench({ api, selectedJob: reviewJob });

  await userEvent.type(screen.getByLabelText(/rejection reason/i), "bad eyes");
  await userEvent.click(screen.getByRole("button", { name: /reject/i }));

  expect(api.rejectReview).toHaveBeenCalledWith(
    reviewJob.id,
    "local-user",
    "bad eyes",
  );
});
```

Add tests for protected-region editing, reference revision selection,
validation diagnostics, lineage traversal, and bundle download path encoding.

- [ ] **Step 2: Run focused component tests**

Run:

```powershell
npm run -w @laqieer/fecreator-web test -- src/review src/canvas src/palette src/lineage src/references src/validation src/reports
```

Expected: current placeholder callbacks and static data fail the assertions.

- [ ] **Step 3: Implement review and editing actions**

`ReviewGallery` accepts typed callbacks and explicit pending/error props.
`MaskEditor` emits:

```typescript
export interface MaskDraft {
  mask_path: string;
  protected_regions: Region[];
}
```

It must preserve keyboard access and never upload in demo mode.

- [ ] **Step 4: Implement validation, lineage, and bundle views**

`ValidationPanel` groups diagnostics by severity and shows the exact target
spec. `LineageView` loads selected node, ancestors, and children.
`ReportBundlePanel` lists sanitized bundle entries and delegates file retrieval
to `ApiClient.getBundleFile()`.

- [ ] **Step 5: Run web tests, commit, and push**

Run:

```powershell
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
```

Then:

```powershell
git add web/src/review web/src/canvas web/src/palette web/src/lineage web/src/references web/src/validation web/src/reports web/src/app/App.tsx
git commit -m "feat(web): wire review tuning and export panels" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 11: Add browser end-to-end flows for local and demo modes

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/e2e/workbench.local.spec.ts`
- Create: `web/e2e/workbench.demo.spec.ts`
- Modify: `web/package.json`
- Modify: `package-lock.json`
- Modify: `src/fecreator/cli.py`
- Modify: `tests/interfaces/test_serve.py`

**Interfaces:**
- Adds `fecreator serve` using existing `Settings.host` and `Settings.port`.
- Adds `test:e2e` and `test:e2e:headed` npm scripts.

- [ ] **Step 1: Write failing serve and browser smoke tests**

```python
def test_serve_binds_configured_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    assert main(["serve"]) == 0
    assert captured["host"] == "127.0.0.1"
```

```typescript
test("demo review flow stays offline", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));

  await page.goto("/FECreator/");
  await page.getByRole("button", { name: /review job/i }).click();
  await page.getByRole("button", { name: /approve/i }).click();

  expect(requests.filter((url) => url.includes("/api/"))).toEqual([]);
});
```

- [ ] **Step 2: Run tests and confirm missing launcher/config**

Run:

```powershell
pytest -q tests/interfaces/test_serve.py
npm run -w @laqieer/fecreator-web test:e2e
```

Expected: missing command/script/config failures.

- [ ] **Step 3: Add the localhost launcher and Playwright configuration**

`serve` creates `FeCreatorApp(Settings.from_env())`, mounts `create_api(app)`,
and calls Uvicorn with the configured localhost host. Playwright launches the
packaged local server for local tests and Vite demo preview for demo tests.

- [ ] **Step 4: Cover approved and rejected flows**

The local flow creates or loads a job, selects it in the queue, reviews a
candidate, approves, finalizes, validates, and opens lineage/report/bundle
panels. A second flow rejects a masked variant and confirms retry creates a new
job. The demo flow covers the same navigation without network APIs.

- [ ] **Step 5: Run, commit, and push**

Run:

```powershell
pytest -q tests/interfaces/test_serve.py
npm run -w @laqieer/fecreator-web build
npm run -w @laqieer/fecreator-web test:e2e
```

Then:

```powershell
git add web/playwright.config.ts web/e2e web/package.json package-lock.json src/fecreator/cli.py tests/interfaces/test_serve.py
git commit -m "test(web): add workbench browser flows" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 12: Add mandatory deterministic FEBuilder-compatible roundtrip evidence

**Files:**
- Create: `src/fecreator/interop/__init__.py`
- Create: `src/fecreator/interop/febuilder_roundtrip.py`
- Create: `tests/interop/test_febuilder_roundtrip.py`
- Modify: `src/fecreator/reporting/bundle.py`
- Modify: `tests/reporting/test_bundle.py`

**Interfaces:**
- Produces
  `decode_roundtrip(package_dir: Path) -> RoundtripEvidence`.
- The probe always runs and never depends on an external executable.

- [ ] **Step 1: Write failing deterministic roundtrip tests**

```python
def test_roundtrip_preserves_indices_palette_and_hashes(tmp_path: Path) -> None:
    package = write_valid_package(tmp_path / "package")

    evidence = decode_roundtrip(package)

    assert evidence.ok is True
    assert evidence.dimensions == (128, 112)
    assert evidence.background_index == 0
    assert evidence.pixel_sha256 == evidence.roundtrip_pixel_sha256
    assert evidence.palette_sha256 == evidence.roundtrip_palette_sha256
```

Add failure cases for RGB PNG, mismatched JASC palette, more than 16 colors,
invalid patch borders, and noncanonical dimensions.

- [ ] **Step 2: Run the interop tests and confirm the module is absent**

Run:

```powershell
pytest -q tests/interop/test_febuilder_roundtrip.py
```

Expected: import failure.

- [ ] **Step 3: Implement the frozen evidence model and roundtrip**

```python
class RoundtripEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    dimensions: tuple[int, int]
    color_count: int
    background_index: int
    pixel_sha256: str
    roundtrip_pixel_sha256: str
    palette_sha256: str
    roundtrip_palette_sha256: str
    diagnostics: tuple[Diagnostic, ...] = ()
```

`decode_roundtrip()` first calls `FeGbaPortraitStandard.validate()`, decodes
indexed pixels and the matching JASC palette, writes a temporary canonical
package under the caller's temporary workspace, reloads it, and compares pixel
arrays, palette arrays, geometry, and hashes. It returns diagnostics instead of
success when any comparison differs.

- [ ] **Step 4: Include mandatory evidence in the reproducibility bundle**

`compat.json` records the deterministic evidence and distinguishes it from
external CLI status. Bundle tests assert no absolute temporary path is included.

- [ ] **Step 5: Run, commit, and push**

Run:

```powershell
pytest -q tests/interop/test_febuilder_roundtrip.py tests/reporting/test_bundle.py
```

Then:

```powershell
git add src/fecreator/interop tests/interop/test_febuilder_roundtrip.py src/fecreator/reporting/bundle.py tests/reporting/test_bundle.py
git commit -m "feat: add deterministic FEBuilder package roundtrip" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 13: Add the optional safe FEBuilderGBA CLI adapter and documentation

**Files:**
- Create: `src/fecreator/interop/febuilder_cli.py`
- Create: `tests/interop/test_febuilder_cli.py`
- Create: `docs/febuilder-interop.md`
- Modify: `src/fecreator/reporting/bundle.py`
- Modify: `tests/reporting/test_bundle.py`

**Interfaces:**
- Produces `run_febuilder_cli(cli_argv, command, package_dir, expect_dir=None)`.
- Missing configuration returns `status="not_run"`.
- Configured nonzero, timeout, or malformed output returns `status="failed"`.

- [ ] **Step 1: Write failing safety and status tests**

```python
def test_missing_cli_is_explicitly_not_run(tmp_path: Path) -> None:
    result = run_febuilder_cli(None, "validate-asset", tmp_path)

    assert result.status == "not_run"
    assert result.exit_code is None


def test_cli_uses_argv_and_redacts_output(tmp_path: Path) -> None:
    result = run_febuilder_cli(
        (sys.executable, str(fake_cli_script(tmp_path))),
        "validate-asset",
        tmp_path,
        env={"PATH": os.environ["PATH"]},
    )

    assert result.status == "passed"
    assert str(tmp_path) not in result.stdout
```

Add timeout, nonzero, missing executable, bounded-output, and environment
allowlist tests.

- [ ] **Step 2: Run the tests and confirm the module is absent**

Run:

```powershell
pytest -q tests/interop/test_febuilder_cli.py
```

Expected: import failure.

- [ ] **Step 3: Implement the safe adapter**

```python
class FeBuilderCliResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["not_run", "passed", "failed"]
    command: Literal["validate-asset", "roundtrip-asset"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


def build_argv(
    cli_argv: Sequence[str],
    command: Literal["validate-asset", "roundtrip-asset"],
    package_dir: Path,
    expect_dir: Path | None = None,
) -> list[str]:
    argv = [
        *cli_argv,
        f"--{command}",
        "--kind=portrait-package",
        f"--path={package_dir}",
    ]
    if expect_dir is not None:
        argv.append(f"--expect={expect_dir}")
    return argv
```

`run_febuilder_cli()` calls
`subprocess.run(argv, capture_output=True, text=True, shell=False,
timeout=timeout_seconds, env=allowed_env, check=False)`, passes only
allowlisted environment keys, bounds output before applying `redact()`, and
never logs the full argv.

- [ ] **Step 4: Document evidence levels and bundle reporting**

`docs/febuilder-interop.md` documents mandatory deterministic evidence,
optional external validation, `FEBUILDER_CLI`, and opt-in user-owned ROM checks.
It explicitly states that ROM-required checks never run in CI.

- [ ] **Step 5: Run, commit, and push**

Run:

```powershell
pytest -q tests/interop tests/reporting/test_bundle.py
```

Then:

```powershell
git add src/fecreator/interop/febuilder_cli.py tests/interop/test_febuilder_cli.py docs/febuilder-interop.md src/fecreator/reporting/bundle.py tests/reporting/test_bundle.py
git commit -m "feat: add optional FEBuilder CLI validation" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 14: Freeze v1 contracts and complete CI and packaging gates

**Files:**
- Create: `docs/v1-contract.md`
- Create: `tests/contracts/test_contract_freeze.py`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `web/src/api/types.contract.test.ts`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_pages_workflow.py`
- Modify: `tests/test_package.py`
- Modify: `README.md`

**Interfaces:**
- Freezes contract version `1.0`, public model fields, workflow literals,
  interface operation names, and target ID.
- Adds required `browser` and `febuilder-interop` CI jobs.

- [ ] **Step 1: Write failing contract-freeze and workflow tests**

```python
def test_v1_public_contract_inventory_is_frozen() -> None:
    assert frozen_contract_inventory() == {
        "Manifest": "1.0",
        "CandidateSnapshot": "1.0",
        "JobResult": "1.0",
        "LineageNode": "1.0",
    }


def test_pages_deploy_requires_all_release_gates(workflow: dict[str, object]) -> None:
    needs = set(workflow["jobs"]["deploy-pages"]["needs"])
    assert {"python", "web", "browser", "package", "febuilder-interop", "secret-scan"} <= needs
```

Add a package test that installs the built wheel and verifies packaged
`fecreator/_web/index.html`.

- [ ] **Step 2: Run focused freeze, workflow, and package tests**

Run:

```powershell
pytest -q tests/contracts/test_contract_freeze.py tests/contracts/test_schemas.py tests/test_ci_pages_workflow.py tests/test_package.py
npm run -w @laqieer/fecreator-web test -- src/api/types.contract.test.ts
```

Expected: missing freeze inventory and CI jobs.

- [ ] **Step 3: Document and enforce the frozen surface**

`docs/v1-contract.md` lists exact public contracts, fields, literals, interface
names, compatibility rules, and the intentional failure behavior for legacy
unpinned jobs. The test imports actual models and compares exact field/literal
sets rather than matching prose.

- [ ] **Step 4: Add browser and interop CI jobs and package smoke**

The `browser` job installs Playwright Chromium and runs `test:e2e`. The
`febuilder-interop` job always runs deterministic roundtrip tests and runs the
external adapter only when `vars.FEBUILDER_CLI` is configured. Pages deployment
depends on all required jobs and remains limited to successful `main` builds.

- [ ] **Step 5: Run release checks, commit, and push**

Run:

```powershell
pytest -q tests/contracts/test_contract_freeze.py tests/contracts/test_schemas.py tests/test_ci_pages_workflow.py tests/test_package.py
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
npm run -w @laqieer/fecreator-web build
python -m build
```

Then:

```powershell
git add docs/v1-contract.md tests/contracts/test_contract_freeze.py tests/contracts/test_schemas.py web/src/api/types.contract.test.ts .github/workflows/ci.yml tests/test_ci_pages_workflow.py tests/test_package.py README.md
git commit -m "chore: freeze v1 release contracts and gates" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

### Task 15: Verify all acceptance criteria and close issue #1

**Files:**
- Modify only files required by failures found during final verification.
- Update GitHub issue #1 after all repository checks and CI pass.

**Interfaces:**
- Produces a green `main` branch and a closed issue with every checklist item
  checked.

- [ ] **Step 1: Run the complete local verification matrix**

Run:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -q
npm run -w @laqieer/fecreator-web typecheck
npm run -w @laqieer/fecreator-web lint
npm run -w @laqieer/fecreator-web test
npm run -w @laqieer/fecreator-web build
npm run -w @laqieer/fecreator-web test:e2e
python -m build
```

Expected: every command exits zero.

- [ ] **Step 2: Verify measurable issue outcomes**

Run targeted end-to-end tests proving:

```text
text_to_portrait -> candidate -> approve -> final package
concept_to_portrait -> candidate -> approve -> final package
expression_refine -> candidate with preserved borders
masked_variant -> protected-region-safe candidate
reject -> failed immutable job -> linked retry job
deterministic FEBuilder-compatible roundtrip
local browser flow and offline demo browser flow
wheel install with packaged web assets
```

- [ ] **Step 3: Push any final fixes immediately**

For each correction, run its focused test, commit only the relevant files with
the required co-author trailer, push immediately, and keep CI monitoring in a
background shell.

- [ ] **Step 4: Wait for the final pushed SHA's required checks**

Use:

```powershell
$sha = git rev-parse HEAD
gh run list --commit $sha --limit 5
```

Monitor the matching run asynchronously. Do not close the issue until `python`,
`web`, `browser`, `package`, `febuilder-interop`, `secret-scan`, and
`deploy-pages` have the expected successful or deployment-gated conclusions.

- [ ] **Step 5: Update and close issue #1**

Fetch the current body, replace every unchecked implementation item with
`[x]`, append links to the completing commits and final CI run, then run:

```powershell
gh issue edit 1 --body-file $updatedBodyPath
gh issue close 1 --comment "FECreator v1 is complete. All required local, browser, package, interoperability, security, and CI checks are green."
```

Do not create a GitHub Release.
