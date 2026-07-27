# Security

This document covers FECreator's secret-scanning guardrails and how to operate
them.

Release credentials are covered separately: FECreator publishes to PyPI with
OIDC Trusted Publishing and stores no publishing token at all, as described in
[`docs/pypi-publishing.md`](pypi-publishing.md).

## GitGuardian alert: synthetic JWT test fixture

A GitGuardian alert was raised for a JWT-shaped value (and an adjacent
AWS-access-key-shaped value) introduced by commit `a997c53` in
`tests/core/test_redaction.py` and `tests/reporting/test_json_report.py`.

### Incident classification: synthetic test fixture (false positive)

Safe inspection of the value confirms it is **not a real credential**:

- the JWT header contains only an `alg` field,
- the payload contains only a `sub` field,
- the signature is a fixed, fake 9-byte value.

It exists purely to exercise the redaction logic, which keys off credential
*shapes*. There is **no real secret, no associated account, and nothing to
revoke or rotate**. This is a **false positive / test credential**.

> The literal token value must never be copied into reports, issues, logs, or
> chat. The two occurrences are referenced only by their SHA256 fingerprints.

### Required manual dashboard action

Automated config changes cannot resolve the dashboard incident. A maintainer
must open the GitGuardian dashboard and **manually mark the incident as a
"Test Credential" / "False Positive"** so it stops surfacing. This is the one
step that cannot be automated from the repository.

### Remediation applied

1. **Removed the scanner-visible literals.** The tests now assemble the
   credential-shaped values at runtime from harmless fragments
   (`tests/fixtures/synthetic_secrets.py`), preserving the exact redaction
   behaviour while leaving no literal secret in the source tree.
2. **Regression guard.** `tests/security/test_no_secret_literals.py` scans every
   tracked text file and fails if a JWT- or AWS-key-shaped literal reappears
   (only generated/vendor/`.git` paths are excluded — the test tree is scanned).
3. **History false positives.** `.gitguardian.yaml` ignores **only** the two
   exact synthetic historical fingerprints (by SHA256, never plaintext), so
   full-history `ggshield` scans stay clean without weakening future detection.

Ignored match fingerprints (safe to commit):

| Fixture              | SHA256 fingerprint                                                 |
| -------------------- | ------------------------------------------------------------------ |
| Synthetic JWT        | `66c5e99a80784da68902affa0beae974f17f53c2112fc933137957ab8a92aa07` |
| Synthetic AWS-shaped | `457643f44d19aed85fd756aa50cc0cd6b57376d4e8f5a72f9f85972a522002a3` |

### Git history is intentionally **not** rewritten

Because the value is a **synthetic fixture with nothing to revoke**, and because
multiple public branches are active, rewriting history (e.g. `filter-repo` /
force-push) would break every contributor's clone and every open branch/PR for
no security benefit. We therefore **deliberately keep history intact** and
suppress the historical false positive via the two fingerprints above. Only
fingerprints — never plaintext secrets — are stored in `.gitguardian.yaml`.

## Scanning layers

| Layer                      | Where it runs               | Covers                         |
| -------------------------- | --------------------------- | ------------------------------ |
| `ggshield` pre-commit hook | Developer machines          | Staged changes before commit   |
| `secret-scan` CI job       | Pushes (all branches) & internal PRs | Commit range in CI    |
| GitGuardian GitHub App     | GitGuardian dashboard       | **Fork PRs** and full history  |

The CI workflow's `on.push` trigger is intentionally unfiltered so secret
scanning runs on pushes to **every branch**, not just `main`. This runs the full
CI matrix on each branch push (a deliberate cost trade-off). Deployment stays
gated to `main` pushes and depends on `secret-scan`, so a failed scan blocks
deploys without weakening that gate.

### Fork pull requests

GitHub does **not** expose repository secrets (including
`GITGUARDIAN_API_KEY`) to workflows triggered by pull requests from forks. The
`secret-scan` CI job therefore **safely skips fork PRs** instead of failing on a
missing key. Fork PRs remain covered by the **GitGuardian GitHub App / dashboard
scanning layer**, which does not rely on Actions secrets. On pushes and internal
(same-repo) PRs the job runs and fails with a clear message if the key is
absent.

## Setup

### 1. Configure the CI secret (maintainers)

Set the API key as an Actions secret. The command below prompts for the value
securely and never echoes it to the terminal or shell history:

```bash
gh secret set GITGUARDIAN_API_KEY --repo laqieer/FECreator
```

Until this secret is set, the `secret-scan` job fails on pushes/internal PRs
with an actionable error (this is expected and by design).

### 2. Install the local pre-commit hook (developers)

```bash
pip install -e ".[dev]"   # installs pre-commit and ggshield
pre-commit install         # installs the git hook (not committed to the repo)
```

### 3. Local ggshield use

`ggshield` reads its key from the environment. Export it locally without
committing it anywhere:

```bash
# bash / zsh
export GITGUARDIAN_API_KEY=...        # paste your personal token

# PowerShell
$env:GITGUARDIAN_API_KEY = "..."
```

Never hard-code the key in files, commits, or chat. `.gitguardian.yaml` sets
`show_secrets: false`, so ggshield will not print matched values.
