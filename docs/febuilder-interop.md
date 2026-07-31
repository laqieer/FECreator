# FEBuilderGBA interoperability

FECreator exports `fe-gba-portrait-standard` packages that FEBuilderGBA can import.
This document describes how that portrait compatibility is *evidenced*, and the
three levels of proof are deliberately kept apart. The optional external CLI adapter
below validates portrait packages only; the dialogue-background source workflow is
scoped separately:

| Level | What it proves | Runs in CI | Needs FEBuilderGBA | Needs a ROM |
| --- | --- | --- | --- | --- |
| 1. Deterministic roundtrip (mandatory) | The published package satisfies the strict spec contract and survives canonical decode/encode/decode unchanged | Yes, always | No | No |
| 2. External CLI validation (optional) | A real FEBuilder-compatible executable accepted the package directory | No | Yes | No |
| 3. ROM import check (opt-in, local only) | A portrait imports into *your* ROM | Never | Yes | Yes, user-owned |

Level 1 is the only mandatory evidence. Levels 2 and 3 are supplementary and can
never replace, weaken, or substitute for it.

## FE8 dialogue-background downstream profile

`fe8-dialogue-background-source-240x160` is an opaque 240×160 **source**
contract, not a FE8 engine package. It accepts RGB, fully opaque RGBA, or indexed
PNG without color-count, palette-index, palette-bank, tile, TSA, or JASC-palette
limits. FECreator neither runs nor validates dialogue downstream conversion at this
stage, and it ships no adapter for this dialogue decreasecolor/TSA profile. That
absence does not change the existing portrait external CLI validation described
below.

The optional `fe8-dialogue-background-feimg2` downstream profile begins outside
FECreator with the Issue #2 command:

```text
FEBuilderGBA.CLI --decreasecolor \
  --in=<source.png> \
  --out=<reduced.png> \
  --paletteno=128 \
  --noReserve1stColor \
  --json
```

The downstream build then owns deterministic indexed-palette assignment and
eight 16-color-bank validation, GBA snapping, per-8×8-tile bank assignment,
fewer-than-`0x400` normal/H/V/HV-deduplicated tiles, a matching 128-entry JASC
palette, and
`fireemblem8-expansion/scripts/gfxtools/tsa_generator.py` conversion to
`.feimg2.bin` and `.fetsa2.bin`. The expansion Makefile remains authoritative
for conversion, compression, linkage, and ROM integration. FECreator does not
duplicate `DecreaseColorCore`, reject valid truecolor sources, or validate
palette banks/TSA constraints. Fixture compatibility evidence is public under
`docs/feature-requests/fe8-dialogue-background/`; it demonstrates this optional
profile rather than imposing its limits on source packages.

## Level 1: mandatory deterministic evidence

`fecreator.interop.febuilder_roundtrip.decode_roundtrip()` validates the canonical
package with the strict target spec, re-encodes it through the indexed-PNG and JASC
boundaries, reloads it, and compares geometry, palette order, background index, and
array hashes.

Every bundle written by `build_bundle()` contains this evidence in `compat.json`:

```json
{
  "source": "deterministic_febuilder_compatible_roundtrip",
  "validated_by_cli": false,
  "external_cli": { "status": "not_run", "command": "validate-asset", "exit_code": null },
  "roundtrip": { "ok": true, "dimensions": [128, 112], "...": "..." }
}
```

`verify_bundle()` re-decodes the bundled package and refuses evidence that does not
describe those exact bytes, so evidence copied from another package cannot verify.
It also refuses *self-inconsistent* success: a successful roundtrip compared a
package against its own re-encoded copy, so `pixel_sha256` must equal
`roundtrip_pixel_sha256`, `palette_sha256` must equal `roundtrip_palette_sha256`,
the dimensions must be 128x112, the palette must hold 1-16 colors, the background
index must be an earned index inside that palette, and no diagnostics may be
present. Anything else is `BUNDLE_INVALID_COMPAT`. The evidence is path-free,
ROM-free, deterministic, and byte-identical across machines and workspaces.

## Level 2: optional external CLI validation

`fecreator.interop.febuilder_cli.run_febuilder_cli()` runs a FEBuilder-compatible
executable against a package directory. It is **off by default**.

```python
from fecreator.interop.febuilder_cli import febuilder_cli_from_env, run_febuilder_cli
from fecreator.reporting.bundle import build_bundle

result = run_febuilder_cli(febuilder_cli_from_env(), "validate-asset", package_dir)
build_bundle(job, workspace, out_dir, febuilder_cli=febuilder_cli_from_env())
```

### Configuration

- `FEBUILDER_CLI` holds the path of one executable and is read only when you ask for
  it (`febuilder_cli_from_env()`); nothing reads it implicitly during job
  finalization, so normal publication stays offline.
- The value is **one argv token**, never shell-split, so
  `C:\Program Files\FEBuilder\fe builder.exe` works unquoted. Multi-token
  invocations such as `("mono", "FEBuilder.exe")` must be passed as a sequence
  through the API.
- Commands are `validate-asset` and `roundtrip-asset`. The adapter builds argv
  itself:

  ```text
  <cli argv...> --validate-asset  --kind=portrait-package --path=<package dir>
  <cli argv...> --roundtrip-asset --kind=portrait-package --path=<package dir> --expect=<expected dir>
  ```

### Status semantics

`run_febuilder_cli()` returns a frozen result with exactly one status:

- `not_run` — no CLI configured. This is an explicit, recorded state, **not** a
  skipped mandatory check.
- `passed` — the process exited `0`.
- `failed` — nonzero exit, timeout, unusable executable, or output that is not
  valid UTF-8.

Unsafe or invalid inputs (unknown command, missing or non-directory package path,
symlinked directory, a path outside the allowed root, an `--expect` directory with
a non-roundtrip command) raise `FeBuilderCliError` instead of degrading into a
success-shaped result.

### Safety properties

- `shell=False` with an explicit argv list; a configured string is one token and is
  never split, so no shell metacharacter can be interpreted.
- Allowlisted environment only (`fecreator.core.process.safe_subprocess_env`), so
  provider credentials and ambient configuration never reach the third-party
  process. `PYTHONIOENCODING` is pinned to `utf-8`.
- Genuinely bounded runtime (`fecreator.core.process.run_bounded_process`). The
  child runs in its own POSIX session or Windows process group; on expiry the whole
  *tree* is terminated by PID (`killpg`, or `taskkill /T /F /PID` -- never a
  name-based kill) and the drain of the captured pipes is itself bounded. A
  grandchild that inherited stdout can therefore neither survive the timeout nor
  block the call, which a plain `subprocess.run(timeout=...)` cannot promise.
- Output is captured as bytes, decoded strictly, redacted, and bounded before it
  leaves the adapter. Redaction removes the exact paths this adapter placed on the
  command line (the CLI tokens, `--path`, `--expect`) first, and only then applies
  generic scrubbing of quoted, flag-valued, and standalone POSIX, Windows, and UNC
  absolute paths. Paths containing spaces and escaped separators are covered, and
  parent directory components are never left behind. The argv itself is never
  logged.
- A configured value that is blank, empty, or contains a NUL is a misconfiguration:
  it raises rather than being reported as `not_run`, and NUL never escapes as a raw
  `ValueError`.
- Directory arguments are resolved, required to be real directories, refused when
  they are links, and refused when they escape the caller's root (the job
  workspace when called from `build_bundle`).

### Reporting semantics

`compat.json` records the external status next to — never merged into — the
mandatory evidence:

- `external_cli.status` is `not_run`, `passed`, or `failed`.
- `validated_by_cli` mirrors `external_cli.status == "passed"` and describes the
  *optional* level only; `source` and `roundtrip` always describe the mandatory
  deterministic proof.
- Only status, command, and exit code are stored. External stdout/stderr stay out
  of bundles because they are environment- and version-specific, which keeps
  bundles sanitized and byte-reproducible.
- If a CLI is configured and the check fails, `build_bundle()` raises `BundleError`
  and publishes nothing. An explicitly requested external validation is never
  downgraded to a warning or a success. The same applies to a configured value that
  cannot be used at all (blank, empty, or containing a NUL): it fails bundle
  creation instead of publishing `not_run`.
- `verify_bundle()` reports `BUNDLE_EXTERNAL_CLI_FAILURE` for a recorded `failed`
  status and `BUNDLE_INVALID_COMPAT` for a malformed or inconsistent block --
  including `status: "failed"` with `exit_code: 0`, which no real run can produce. A
  passing CLI never suppresses `BUNDLE_COMPAT_FAILURE` from the mandatory roundtrip.

### Bundle format compatibility

The `external_cli` block is **required**. A bundle produced before it was
introduced has no such block, so `verify_bundle()` reports `BUNDLE_INVALID_COMPAT`
(`compat.json has malformed external CLI evidence`) and the bundle does not verify.
This is deliberate fail-closed behaviour rather than a regression: verification
must not assume the missing level-2 status. Republish affected bundles with
`build_bundle()` -- the deterministic level-1 evidence is unchanged, so the
regenerated bundle is byte-identical apart from the added block.

## Level 3: ROM import checks (opt-in, local only)

Importing a portrait into an actual GBA ROM can only be verified by you, locally,
with your own legally obtained ROM.

- FECreator never reads, writes, bundles, hashes, or records a ROM path or ROM
  content.
- No ROM-dependent check runs in CI, in tests, or as part of bundle creation, and
  no ROM-related environment variable is forwarded to a child process.
- Never commit a ROM, a ROM path, or a ROM-derived artifact to this repository.

Suggested manual workflow:

1. Publish the job and confirm the bundle verifies (`verify_bundle()` returns no
   diagnostics).
2. Optionally run level 2 against your local FEBuilder-compatible CLI.
3. Open FEBuilderGBA with your own ROM, import `package/<name>.png` plus the
   same-basename `.pal`, and confirm the portrait renders as expected.

Results of step 3 are yours alone; report them as prose in an issue, never as
files, paths, or ROM data.

## Testing

Level 2 is covered by `tests/interop/test_febuilder_cli.py` using a fake CLI
script invoked through argv. The suite covers argv construction, paths containing
spaces (proved by what the child resolves, not by echoing paths back), missing
executables, timeouts including termination of a grandchild that inherited the
captured stdout pipe, nonzero exits, output bounds, redaction of real emitted
absolute paths and runtime-constructed synthetic credentials on both streams, the
environment allowlist, NUL rejection, undecodable output, containment, and
success. The shared process boundary is covered by `tests/core/test_process.py`.
No test requires FEBuilderGBA or a ROM to be installed.

## Continuous integration

The `febuilder-interop` CI job runs on every push and pull request:

- it **always** runs the deterministic level-1 tests
  (`tests/interop/test_febuilder_roundtrip.py`, `tests/interop/test_febuilder_cli.py`,
  and `tests/reporting/test_bundle.py`);
- it additionally runs `tests/interop/test_febuilder_cli_smoke.py` when the
  `FEBUILDER_CLI` **repository variable** is a non-empty executable path. That
  smoke check builds a canonical package in a temporary directory, asks the
  configured executable to validate it, and fails the job on any nonzero exit.
  Locally the same test skips itself unless `FEBUILDER_CLI` is set.

Level 3 never runs in CI. No job requires, downloads, or references a ROM.
