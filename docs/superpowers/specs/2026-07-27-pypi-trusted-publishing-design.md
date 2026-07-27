# PyPI Trusted Publishing Design

**Status:** Approved

## Goal

Publish the `fecreator` Python distribution to PyPI without storing a PyPI API
token in GitHub or on developer machines.

## Authentication

Publishing uses PyPI Trusted Publishing through GitHub Actions OIDC.

- PyPI project: `fecreator`
- GitHub owner: `laqieer`
- GitHub repository: `FECreator`
- Workflow: `.github/workflows/publish.yml`
- GitHub environment: `pypi`

The PyPI project does not exist yet. The maintainer creates a pending publisher
from the authenticated PyPI account. The first successful workflow run creates
the project and converts the pending publisher into a normal trusted publisher.

No username, password, API token, or publishing credential is stored in GitHub
Secrets, repository files, manifests, bundles, or local configuration.

## Workflow architecture

The workflow has two jobs with separate trust boundaries.

### Build job

The build job has read-only repository permissions and no OIDC permission.

1. Check out `refs/tags/<selected tag>` with `persist-credentials: false`.
2. Verify the tag is exactly `v<project version>`.
3. Install the supported Python and Node toolchains without a restored pip
   cache.
4. Install locked npm dependencies.
5. Build the local web assets into `src/fecreator/_web`.
6. Build the wheel and source distribution.
7. Validate both files with `twine check --strict`.
8. Run the repository packaging test, which re-proves the packaging invariants
   with isolated probe builds before upload.
9. Upload the immutable `dist/` directory as a GitHub Actions artifact.

The checkout ref is fully qualified so a branch cannot shadow the tag.

Build tools and project code never receive an OIDC token.

### Publish job

The publish job:

- runs on GitHub-hosted Ubuntu
- depends on the build job
- uses the protected `pypi` GitHub environment
- has only `id-token: write` and `contents: read`
- downloads the previously built distributions
- publishes with the official PyPA action
- uploads PyPI digital attestations through Trusted Publishing with an explicit
  `attestations: true`

The PyPA action is pinned to an immutable commit SHA.

### Run hygiene

Both jobs declare `timeout-minutes`. The workflow serializes runs of one tag
with concurrency group `publish-${{ github.ref_name }}` and
`cancel-in-progress: false`, so a second run queues instead of interrupting an
upload in flight.

## Triggers

The workflow supports:

- pushes of semantic version tags matching `v*.*.*`
- manual dispatch **on an existing tag**, with no workflow input

`RELEASE_TAG` is exactly `${{ github.ref_name }}`, and the checkout ref is
`refs/tags/${{ env.RELEASE_TAG }}`. A manual run is therefore started with
`gh workflow run publish.yml --ref v0.1.0`: GitHub resolves the ref, so no
free-form string can name a ref the trigger never vetted. Both trigger paths
validate that the tag version matches `pyproject.toml` and
`fecreator.__version__`.

## Release tag history

The `v0.1.0` tag that exists today predates `publish.yml` and
`scripts/validate_release_tag.py`, so it cannot be published as-is. Version
`0.1.0` has never been uploaded to PyPI, so exactly once — before the first
publication — the unpublished tag is deleted and recreated at the final merge
commit of this work. From then on the tag is immutable: a published version is
never re-uploaded, moved, or recreated, and a mistake is corrected by releasing
a new version.

## GitHub environment

The repository has a `pypi` environment, and its protection rules are required,
not advisory:

- a required reviewer, `laqieer`, must approve every deployment
- a custom deployment tag policy limits deployments to refs matching `v*.*.*`

The publisher identity remains the environment `pypi` named in the PyPI pending
publisher. The workflow requires no stored environment secret.

## Failure behavior

- A missing or malformed tag fails before building.
- A tag/version mismatch fails before artifact upload.
- Missing web assets fail the Python build.
- Invalid distributions fail `twine check --strict`.
- A packaging invariant regression fails `tests/test_package.py` before upload.
- An unapproved deployment never reaches the publish job.
- Missing or mismatched PyPI trusted-publisher configuration fails the publish
  job without falling back to a token.
- A version already present on PyPI fails; existing files are never skipped or
  overwritten.
- Publishing never creates a GitHub Release.

## Testing

Repository tests verify:

- tag parsing and project-version matching
- the workflow's triggers, the absence of a dispatch tag input, the exact
  `RELEASE_TAG` expression and qualified checkout ref, permissions, environment,
  job separation, artifact handoff, concurrency, timeouts, and immutable action
  pin
- checkout credential settings, absence of a restored pip cache, strict Twine
  validation, the packaging test's position before upload, and explicit
  attestations
- absence of PyPI token or password configuration
- build-before-publish ordering and the packaging test's isolated probe builds
- no GitHub Release step
- documentation of the pending publisher fields, the required environment
  protection rules, the one-time `v0.1.0` recreation, and the manual dispatch
  command

The OIDC exchange itself cannot be exercised in ordinary CI. The first real
publish verifies the pending publisher and creates the PyPI project.

## Maintainer setup

One authenticated PyPI action remains intentionally outside repository
automation:

1. Open <https://pypi.org/manage/account/publishing/>.
2. Add a pending GitHub publisher for project `fecreator`.
3. Enter owner `laqieer`, repository `FECreator`, workflow `publish.yml`, and
   environment `pypi`.
4. Configure the `pypi` environment with the required reviewer `laqieer` and a
   custom deployment tag policy `v*.*.*`.
5. Recreate the unpublished `v0.1.0` tag at the final merge commit, once.
6. Run the workflow for tag `v0.1.0`.

This step proves control of the PyPI account without exposing credentials to
the assistant or repository.
