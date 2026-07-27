# Publishing FECreator to PyPI

FECreator is published with [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).
No PyPI API token, password, or long-lived credential exists anywhere in this
repository or in GitHub Actions secrets. Releases are minted from a short-lived
OpenID Connect (OIDC) token that PyPI issues only to one workflow, in one
repository, in one environment.

## Trust boundary

`.github/workflows/publish.yml` splits the release into two jobs:

| Job | Permissions | Responsibility |
| --- | --- | --- |
| `build` | `contents: read` | Checks out the release tag, validates versions, builds the web bundle, builds the wheel/sdist, runs `twine check`, uploads the `python-distributions` artifact. |
| `publish` | `contents: read`, `id-token: write` | Downloads only `python-distributions` and uploads it to PyPI through the pinned PyPA action. |

Consequences of that split:

- The privileged OIDC token is job-scoped. The workflow's default permissions
  are `contents: read`, and only `publish` adds `id-token: write`.
- `publish` never checks out the repository and runs no `run` steps, so no
  project code, dependency, or build script executes while the token exists.
- The publishing action is pinned to an immutable commit SHA
  (`pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247`), so a
  moving tag cannot change what runs next to the token.
- `skip-existing` is not enabled: republishing an already-published version
  fails loudly instead of appearing to succeed.
- The workflow does not create GitHub Releases, does not touch ROMs, and does
  not read any repository secret.

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

Then create the matching GitHub environment named `pypi`
(<https://github.com/laqieer/FECreator/settings/environments>). Restricting that
environment to protected tags, and requiring a reviewer, is recommended: PyPI
only trusts tokens whose claims include this environment.

Any mismatch — a different workflow file name, a renamed repository, or a
missing environment — makes PyPI reject the token, and the `publish` job fails
without uploading anything.

## Releasing

1. Land the version bump on `main`: `pyproject.toml` `project.version` and
   `src/fecreator/__init__.py` `__version__` must be the same canonical
   `MAJOR.MINOR.PATCH` value.
2. Tag the release commit and push the tag:

   ```powershell
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The tag push starts `publish.yml`, which checks out that exact tag.
3. `python scripts/validate_release_tag.py --tag "$RELEASE_TAG"` runs before any
   artifact is built and fails when the tag, `pyproject.toml`, and
   `src/fecreator/__init__.py` do not agree exactly.
4. Approve the `pypi` environment deployment if a reviewer is required, then
   confirm the distributions at <https://pypi.org/p/fecreator>.

## Re-running a release manually

A manual run publishes an **existing** tag; it never creates one. The tag input
selects the checked-out ref, so a manual run and a tag push build the same
immutable source:

```powershell
gh workflow run publish.yml --ref main -f tag=v0.1.0
```

Use this when the tag push run failed after the tag was already correct (for
example a transient network failure). If the version was wrong, delete the bad
tag, fix the versions, and tag again — PyPI never allows re-uploading a version
that already exists.
