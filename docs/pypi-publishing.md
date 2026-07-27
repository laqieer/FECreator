# Publishing FECreator to PyPI

FECreator is published with [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).
No PyPI API token, password, or long-lived credential exists anywhere in this
repository or in GitHub Actions secrets. Releases are minted from a short-lived
OpenID Connect (OIDC) token that PyPI issues only to one workflow, in one
repository, in one environment. Repository-wide credential handling is
described in [`docs/security.md`](security.md).

## Trust boundary

`.github/workflows/publish.yml` splits the release into two jobs:

| Job | Permissions | Responsibility |
| --- | --- | --- |
| `build` | `contents: read` | Checks out the release tag, validates versions, builds the web bundle, builds the wheel/sdist, runs `twine check --strict` and the real packaging test, uploads the `python-distributions` artifact. |
| `publish` | `contents: read`, `id-token: write` | Downloads only `python-distributions` and uploads it to PyPI through the pinned PyPA action. |

Consequences of that split:

- The privileged OIDC token is job-scoped. The workflow's default permissions
  are `contents: read`, and only `publish` adds `id-token: write`.
- `publish` never checks out the repository and runs no `run` steps, so no
  project code, dependency, or build script executes while the token exists.
- The publishing action is pinned to an immutable commit SHA
  (`pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247`), so a
  moving tag cannot change what runs next to the token.
- `attestations: true` is set explicitly, so PyPI digital attestations are a
  pinned property of this workflow rather than an inherited action default.
- `skip-existing` is not enabled: republishing an already-published version
  fails loudly instead of appearing to succeed.
- The workflow does not create GitHub Releases, does not touch ROMs, and does
  not read any repository secret.

### Release hardening

- **Qualified tag checkout.** The build job checks out
  `refs/tags/${{ env.RELEASE_TAG }}`. An unqualified ref would let a branch with
  the same name shadow the tag and publish unreviewed code.
- **No tag input.** `RELEASE_TAG` is exactly `${{ github.ref_name }}`. Both a tag
  push and a manual `--ref` run publish a ref that GitHub resolved, so a run
  cannot name an arbitrary string.
- **No persisted git credential.** The checkout sets
  `persist-credentials: false`, so the build steps run without an authenticated
  git remote.
- **No restored pip cache.** The build resolves dependencies fresh; a release
  build does not trust a cache another workflow run wrote.
- **Real packaging proof before upload.** `pytest -q tests/test_package.py` runs
  against the distributions that were just built, before they leave the job as
  an artifact.
- **Strict metadata validation.** `twine check --strict` turns a README
  rendering warning into a failure.
- **Serialized runs.** Concurrency group `publish-${{ github.ref_name }}` with
  `cancel-in-progress: false` queues a second run of the same tag instead of
  cancelling an upload in flight.
- **Bounded jobs.** Both jobs declare `timeout-minutes`, so a hung release
  cannot hold the environment open.

`tests/test_pypi_publish_workflow.py` enforces every property above, so a
regression fails CI rather than a release.

## One-time pending publisher setup

Before the first release, a maintainer creates a **pending publisher** on
<https://pypi.org/manage/account/publishing/> using exactly these values:

```text
Project: fecreator
Owner: laqieer
Repository: FECreator
Workflow: publish.yml
Environment: pypi
```

Any mismatch — a different workflow file name, a renamed repository, or a
missing environment — makes PyPI reject the token, and the `publish` job fails
without uploading anything.

## Required environment protection

The GitHub environment `pypi`
(<https://github.com/laqieer/FECreator/settings/environments>) is the human gate
in front of the OIDC token, so its protection rules are required, not optional:

- **Required reviewer: `laqieer`.** No deployment to `pypi` — and therefore no
  PyPI token — starts without an explicit human approval.
- **Custom deployment tag policy `v*.*.*`.** Only refs matching that pattern may
  deploy to the environment, so a branch can never reach the publish job.

The publisher identity stays the environment `pypi` named in the pending
publisher above; the protection rules constrain who and what may use it.

Configure both with the authenticated CLI:

```powershell
# Require a reviewer and switch to custom (non-branch) deployment policies.
gh api --method PUT repos/laqieer/FECreator/environments/pypi `
  -f 'reviewers[][type]=User' `
  -F "reviewers[][id]=$(gh api users/laqieer --jq .id)" `
  -F 'deployment_branch_policy[protected_branches]=false' `
  -F 'deployment_branch_policy[custom_branch_policies]=true'

# Allow only semantic version tags to deploy.
gh api --method POST repos/laqieer/FECreator/environments/pypi/deployment-branch-policies `
  -f name='v*.*.*' -f type=tag
```

Verify afterwards:

```powershell
gh api repos/laqieer/FECreator/environments/pypi --jq '.protection_rules'
gh api repos/laqieer/FECreator/environments/pypi/deployment-branch-policies
```

## The `v0.1.0` tag

The `v0.1.0` tag that exists today predates `publish.yml`,
`scripts/validate_release_tag.py`, and this guide: it points at a commit where
none of the release machinery exists, so a run of that tag would check out a
tree without the workflow's own inputs.

Because `0.1.0` has never been published to PyPI, nothing downstream depends on
that tag object yet. Exactly once, before the first publication, the maintainer
will delete the unpublished tag and recreate it on the final merge commit of
this work:

```powershell
git push origin :refs/tags/v0.1.0
git tag -d v0.1.0
git tag v0.1.0 <final-merge-commit>
git push origin v0.1.0
```

After that single reset the tag is immutable: once a version exists on PyPI it
is never re-uploaded, moved, or recreated. A wrong version is corrected by
releasing a new version, never by moving a published tag.

## Releasing

1. Land the version bump on `main`: `pyproject.toml` `project.version` and
   `src/fecreator/__init__.py` `__version__` must be the same canonical
   `MAJOR.MINOR.PATCH` value.
2. Tag the release commit and push the tag:

   ```powershell
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The tag push starts `publish.yml`, which checks out
   `refs/tags/v0.1.0` exactly.
3. `python scripts/validate_release_tag.py --tag "$RELEASE_TAG"` runs before any
   artifact is built and fails when the tag, `pyproject.toml`, and
   `src/fecreator/__init__.py` do not agree exactly.
4. Approve the `pypi` environment deployment as the required reviewer, then
   confirm the distributions at <https://pypi.org/p/fecreator>.

## Re-running a release manually

A manual run publishes an **existing** tag; it never creates one. The workflow
takes no tag input — the run is dispatched *on* the tag, and the qualified
`refs/tags/` checkout builds the same immutable source a tag push would:

```powershell
gh workflow run publish.yml --ref v0.1.0
```

Use this when the tag push run failed after the tag was already correct (for
example a transient network failure). If the version was wrong, delete the bad
tag, fix the versions, and tag again — PyPI never allows re-uploading a version
that already exists.
