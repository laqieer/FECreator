from pydantic import BaseModel

from fecreator.core.clock import utc_now_iso
from fecreator.core.hashing import content_hash, sha256_bytes, sha256_file


class _M(BaseModel):
    a: int
    b: str


def test_sha256_bytes_known_vector() -> None:
    assert sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_file_matches_bytes(tmp_path) -> None:
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == sha256_bytes(b"abc")


def test_content_hash_is_field_order_independent() -> None:
    assert content_hash(_M(a=1, b="x")) == content_hash(_M(b="x", a=1))


def test_utc_now_iso_has_utc_suffix() -> None:
    assert utc_now_iso().endswith("+00:00") or utc_now_iso().endswith("Z")
