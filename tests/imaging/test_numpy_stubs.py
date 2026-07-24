"""Regression tests ensuring the real NumPy stubs (not Any-typed shim) are active.

NumPy >= 2.5 bundles stubs using PEP 695 `type` syntax (Python 3.12+) which
mypy cannot parse under python_version = "3.11".  The dev extra pins numpy<2.5
so the bundled stubs are Python-3.11-compatible.  This module verifies both
that the shim is absent and that the installed numpy version satisfies the
type-checking constraint.
"""

from __future__ import annotations


def test_numpy_stub_shim_absent() -> None:
    """The stubs/numpy/ Any-typed shim must not be present in the repository."""
    from pathlib import Path

    # Two possible project roots (worktrees share git objects but may differ)
    shim = Path(__file__).resolve().parent.parent.parent / "stubs" / "numpy"
    assert not shim.exists(), (
        f"stubs/numpy/ shim must be removed from the repo: {shim}\n"
        "Real numpy stubs are used instead via the dev extra numpy<2.5 constraint."
    )


def test_numpy_dev_version_allows_mypy_311() -> None:
    """numpy must be >=2.1,<2.5 so bundled stubs parse under mypy python_version=3.11.

    numpy 2.5.0 introduced 65+ PEP 695 `type X = Y` statements in its stubs.
    numpy 2.1–2.4 stubs have zero such statements (verified empirically).
    The dev extra pins numpy<2.5 to ensure the installed stubs work with
    python_version=3.11 without any shim or ignore_errors workaround.
    """
    import numpy

    parts = tuple(int(x) for x in numpy.__version__.split(".")[:2])
    assert parts >= (2, 1), f"numpy {numpy.__version__} is too old; need >=2.1 for the imaging APIs"
    assert parts < (2, 5), (
        f"numpy {numpy.__version__} stubs use PEP 695 'type' syntax incompatible "
        "with mypy python_version=3.11; pin numpy<2.5 in [project.optional-dependencies] dev"
    )
