import pytest

from app.github import webhooks
from app.github.signature import compute_signature
from tests.constants import TEST_WEBHOOK_SECRET

URL = "/webhooks/github"
BODY = b'{"action":"opened","number":1}'


def signed_headers(body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> dict[str, str]:
    return {
        "X-Hub-Signature-256": compute_signature(body, secret),
        "X-GitHub-Event": "pull_request",
        "Content-Type": "application/json",
    }


def test_valid_signature_is_accepted(client):
    response = client.post(URL, content=BODY, headers=signed_headers(BODY))

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_missing_signature_is_rejected(client):
    response = client.post(URL, content=BODY, headers={"X-GitHub-Event": "pull_request"})

    assert response.status_code == 401


def test_wrong_secret_is_rejected(client):
    response = client.post(URL, content=BODY, headers=signed_headers(BODY, "w" * 32))

    assert response.status_code == 401


def test_tampered_body_is_rejected(client):
    headers = signed_headers(BODY)

    response = client.post(URL, content=b'{"action":"closed","number":1}', headers=headers)

    assert response.status_code == 401


def test_rejection_does_not_leak_details(client):
    response = client.post(URL, content=BODY, headers={"X-Hub-Signature-256": "sha256=00"})

    assert response.json() == {"detail": "Invalid signature"}
    assert compute_signature(BODY, TEST_WEBHOOK_SECRET) not in response.text


def test_oversized_body_is_rejected_before_signature_check(client, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_BODY_BYTES", 10)
    body = b"x" * 11  # one byte over the limit

    response = client.post(URL, content=body, headers=signed_headers(body))

    assert response.status_code == 413


def test_body_at_size_limit_is_accepted(client, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_BODY_BYTES", 10)
    body = b"x" * 10  # exactly at the limit

    response = client.post(URL, content=body, headers=signed_headers(body))

    assert response.status_code == 202


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_only_post_is_allowed(client, method):
    response = client.request(method, URL)

    assert response.status_code == 405
