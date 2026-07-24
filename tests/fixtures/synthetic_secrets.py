"""Runtime builders for synthetic, scanner-shaped secrets used in tests.

These helpers assemble credential-*shaped* strings from harmless fragments at
runtime so the values never appear as literals in the source tree.  That keeps
secret scanners (GitGuardian/ggshield) from flagging the test suite while still
exercising the real redaction behaviour, which keys off the credential shapes.

None of the values produced here are real credentials: the JWT carries only an
``alg`` header and a ``sub`` payload with a fixed, non-secret signature, and the
AWS-shaped value is a deterministic placeholder built from a static alphabet.
"""

from __future__ import annotations

import base64
import json


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def synthetic_jwt() -> str:
    """Return a JWT-shaped token assembled at runtime (never a real secret)."""

    header = _b64url(json.dumps({"alg": "HS256"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"sub": "fixture"}, separators=(",", ":")).encode())
    signature = _b64url(b"synthetic")
    return ".".join((header, payload, signature))


def synthetic_aws_key() -> str:
    """Return an AWS-access-key-shaped placeholder assembled at runtime."""

    prefix = "AK" + "IA"
    body = "".join(chr(ord("A") + (i % 26)) for i in range(16))
    return prefix + body
