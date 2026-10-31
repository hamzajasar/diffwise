import pytest

from app.github.signature import compute_signature, is_valid_signature

SECRET = "s" * 32
BODY = b'{"action":"opened"}'


def test_valid_signature_is_accepted():
    assert is_valid_signature(BODY, compute_signature(BODY, SECRET), SECRET)


def test_matches_githubs_documented_example():
    # Test vector from GitHub's "Validating webhook deliveries" docs: proves we
    # compute signatures exactly the way GitHub does, not just consistently with ourselves.
    expected = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"

    assert compute_signature(b"Hello, World!", "It's a Secret to Everybody") == expected


def test_empty_body_with_valid_signature_is_accepted():
    assert is_valid_signature(b"", compute_signature(b"", SECRET), SECRET)


def test_signed_with_wrong_secret_is_rejected():
    signature = compute_signature(BODY, "w" * 32)

    assert not is_valid_signature(BODY, signature, SECRET)


def test_tampered_body_is_rejected():
    signature = compute_signature(BODY, SECRET)

    assert not is_valid_signature(b'{"action":"closed"}', signature, SECRET)


@pytest.mark.parametrize(
    "header",
    [
        None,  # header missing
        "",  # header present but empty
        "sha256=",  # prefix only
        "deadbeef",  # no prefix
        "sha1=" + "0" * 40,  # old algorithm GitHub also sends: we only accept sha256
        "sha256=" + "0" * 64,  # right shape, wrong value
        "sha256=ünïcödé",  # non-ASCII: must be rejected, not crash
    ],
)
def test_malformed_or_missing_header_is_rejected(header):
    assert not is_valid_signature(BODY, header, SECRET)


def test_truncated_signature_is_rejected():
    signature = compute_signature(BODY, SECRET)

    assert not is_valid_signature(BODY, signature[:-1], SECRET)
