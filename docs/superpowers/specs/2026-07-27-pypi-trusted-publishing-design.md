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

1. Check out the selected version tag.
2. Verify the tag is exactly `v<project version>`.
3. Install the supported Python and Node toolchains.
4. Install locked npm dependencies.
5. Build the local web assets into `src/fecreator/_web`.
6. Build the wheel and source distribution.
7. Validate both files with Twine.
8. Upload the immutable `dist/` directory as a GitHub Actions artifact.

Build tools and project code never receive an OIDC token.

### Publish job

The publish job:

- runs on GitHub-hosted Ubuntu
- depends on the build job
- uses the protected `pypi` GitHub environment
- has only `id-token: write` and `contents: read`
- downloads the previously built distributions
- publishes with the official PyPA action
- uploads PyPI digital attestations through Trusted Publishing

The PyPA action is pinned to an immutable commit SHA.

## Triggers

The workflow supports:

- pushes of semantic version tags matching `v*.*.*`
- manual dispatch with an explicit existing version tag

Manual dispatch checks out the requested tag, not the default branch. Both
trigger paths validate that the tag version matches `pyproject.toml` and
`fecreator.__version__`.

This permits publishing the already-created `v0.1.0` tag after the pending
publisher is configured, without moving or recreating the tag.

## GitHub environment

The repository has a `pypi` environment. Environment protection rules are
maintainer-configurable; the workflow does not require a stored environment
secret.

## Failure behavior

- A missing or malformed tag fails before building.
- A tag/version mismatch fails before artifact upload.
- Missing web assets fail the Python build.
- Invalid distributions fail Twine validation.
- Missing or mismatched PyPI trusted-publisher configuration fails the publish
  job without falling back to a token.
- A version already present on PyPI fails; existing files are never skipped or
  overwritten.
- Publishing never creates a GitHub Release.

## Testing

Repository tests verify:

- tag parsing and project-version matching
- the workflow's trigger, permissions, environment, job separation, artifact
  handoff, and immutable action pin
- absence of PyPI token or password configuration
- build-before-publish ordering
- no GitHub Release step

The OIDC exchange itself cannot be exercised in ordinary CI. The first real
publish verifies the pending publisher and creates the PyPI project.

## Maintainer setup

One authenticated PyPI action remains intentionally outside repository
automation:

1. Open <https://pypi.org/manage/account/publishing/>.
2. Add a pending GitHub publisher for project `fecreator`.
3. Enter owner `laqieer`, repository `FECreator`, workflow `publish.yml`, and
   environment `pypi`.
4. Run the workflow for tag `v0.1.0`.

This step proves control of the PyPI account without exposing credentials to
the assistant or repository.
