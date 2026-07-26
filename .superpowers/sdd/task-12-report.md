# Task 12: Deterministic FEBuilder-Compatible Roundtrip Evidence

## Outcome

Implemented a mandatory, ROM-free deterministic compatibility probe for canonical
`fe-gba-portrait-standard` packages. It does not invoke or claim validation by an
external FEBuilder CLI; that remains Task 13 scope.

## RED / GREEN Evidence

- **RED:** `pytest -q tests\interop\test_febuilder_roundtrip.py` initially failed
  during collection with `ModuleNotFoundError: fecreator.interop`.
- **GREEN:** the new interop suite passed after implementing the probe.
- **Hash regression RED:** the corrupt-reload test failed until the probe emitted
  `ROUNDTRIP_PIXEL_HASH_MISMATCH`; it then passed after canonical hash comparison
  was added.
- Integration coverage passed for interop, reporting-bundle, and strict package
  validation tests.

## Evidence Definition

`RoundtripEvidence` is frozen and extra-forbid. It records the dimensions, color
count, background index, source and reloaded pixel SHA-256 values, source and
reloaded ordered-JASC-palette SHA-256 values, and sorted diagnostics.

- Pixel hashes are SHA-256 of contiguous `uint8` indexed-pixel array bytes.
- Palette hashes are SHA-256 of contiguous `uint8`, ordered `(N, 3)` JASC RGB
  array bytes.
- Strict validation establishes the opaque indexed-PNG, dimensions, palette,
  index-0 background, and canonical geometry contract before any decode.
- The probe revalidates the temporary package, reloads it through existing indexed
  PNG and JASC boundaries, and fails closed on geometry, color-count, palette,
  array, or hash differences.

## Temporary and Reproducibility Design

The probe writes `roundtrip.png` and `roundtrip.pal` inside a
`TemporaryDirectory` outside the input package. The context manager removes the
directory on success and exceptions. Temporary paths are never placed in evidence;
diagnostics are redacted/sanitized and sorted. Bundle JSON is canonicalized through
the existing sorted JSON writer, and the reproducibility test proves identical
`compat.json` and `hashes.json` bytes for equivalent workspaces.

## Tests and Results

- `C:\Projects\FECreator\.venv\Scripts\python.exe -m pytest -q tests\interop\test_febuilder_roundtrip.py tests\reporting\test_bundle.py tests\specs\test_validation.py` — passed.
- `C:\Projects\FECreator\.venv\Scripts\python.exe -m ruff check .` — passed.
- `C:\Projects\FECreator\.venv\Scripts\python.exe -m ruff format --check .` — passed.
- `C:\Projects\FECreator\.venv\Scripts\python.exe -m mypy src` — passed.
- `C:\Projects\FECreator\.venv\Scripts\python.exe -m pytest -q` — passed. The
  existing FastAPI/Starlette deprecation warning remains.

Negative coverage includes RGB input, mismatched JASC palettes, more than 16
colors, invalid background borders, invalid dimensions, corrupt reloads, a restrictive
image budget, and symlinked input paths. Bundle verification covers missing, false,
and hash-tampered compatibility evidence.

## Files Changed

- Added `src/fecreator/interop/__init__.py`
- Added `src/fecreator/interop/febuilder_roundtrip.py`
- Added `tests/interop/test_febuilder_roundtrip.py`
- Updated `src/fecreator/reporting/bundle.py`
- Updated `tests/reporting/test_bundle.py`

## Commit and Push

Implementation commit `7a26f19` (`feat: add deterministic FEBuilder package
roundtrip`) includes the required Copilot co-author trailer and was pushed to
`origin/issue-1-completion` immediately after verification. This report is committed
and pushed separately so it can record that exact implementation commit.

## Self-Review, Deviations, and Concerns

Self-review confirmed that the probe uses existing validation, indexed PNG, JASC,
hashing, redaction, and atomic bundle boundaries; it does not use Pillow for a
quality transform or expose temporary paths. `compat.json` is required and verified,
but its `validated_by_cli` field remains explicitly `false`.

There are no scope deviations. The only concern is the pre-existing upstream
FastAPI/Starlette test-client deprecation warning reported by the full test suite.
