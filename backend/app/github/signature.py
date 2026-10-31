"""Verify that a webhook really came from GitHub (HMAC-SHA256 signature check).

GitHub signs each webhook body with our shared secret and sends the result in the
`X-Hub-Signature-256` header as `sha256=<hex digest>`. We recompute it and compare.
"""

import hashlib
import hmac

SIGNATURE_PREFIX = "sha256="


def compute_signature(body: bytes, secret: str) -> str:
    """Return the signature GitHub would send for this body, e.g. `sha256=3f9a...`."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def is_valid_signature(body: bytes, signature_header: str | None, secret: str) -> bool:
    """True only if the header is present and matches the body signed with our secret."""
    if not signature_header:
        return False
    expected = compute_signature(body, secret)
    # Constant-time comparison: `==` would leak, via timing, how many characters match.
    # Compare as bytes so unusual (non-ASCII) header values can't raise an error.
    return hmac.compare_digest(expected.encode(), signature_header.encode())
