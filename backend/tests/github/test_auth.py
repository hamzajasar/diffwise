import time
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.github.auth import (
    GITHUB_API,
    GitHubAuthError,
    create_app_jwt,
    get_installation_token,
)
from tests.constants import TEST_APP_ID

INSTALLATION_ID = 178198846
TOKEN_URL = f"{GITHUB_API}/app/installations/{INSTALLATION_ID}/access_tokens"


@pytest.fixture
def public_key(private_key_pem):
    return serialization.load_pem_private_key(private_key_pem.encode(), password=None).public_key()


# --- Step 1: the app JWT ---


def test_jwt_is_rs256_and_verifies_with_the_apps_public_key(private_key_pem, public_key):
    token = create_app_jwt(TEST_APP_ID, private_key_pem)

    claims = jwt.decode(token, public_key, algorithms=["RS256"])

    assert jwt.get_unverified_header(token)["alg"] == "RS256"
    assert claims["iss"] == str(TEST_APP_ID)


def test_jwt_timestamps_respect_githubs_limits(private_key_pem):
    now = 1_800_000_000

    claims = jwt.decode(
        create_app_jwt(TEST_APP_ID, private_key_pem, now=now),
        options={"verify_signature": False},
    )

    assert claims["iat"] == now - 60  # backdated for clock skew
    assert claims["exp"] > now  # valid right now
    assert claims["exp"] - now <= 10 * 60  # GitHub's maximum lifetime


def test_jwt_signed_with_another_key_is_rejected(private_key_pem):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    token = create_app_jwt(TEST_APP_ID, private_key_pem)

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other_key, algorithms=["RS256"])


def test_jwt_is_currently_valid(private_key_pem, public_key):
    token = create_app_jwt(TEST_APP_ID, private_key_pem, now=int(time.time()))

    jwt.decode(token, public_key, algorithms=["RS256"])  # raises if expired or not yet valid


# --- Step 2: exchanging the JWT for an installation token (GitHub is mocked) ---


@pytest.mark.anyio
async def test_exchanges_jwt_for_installation_token(respx_mock):
    route = respx_mock.post(TOKEN_URL).respond(
        201, json={"token": "ghs_example", "expires_at": "2026-11-04T12:00:00Z"}
    )

    async with httpx.AsyncClient() as client:
        result = await get_installation_token(client, "app.jwt.value", INSTALLATION_ID)

    assert result.token.get_secret_value() == "ghs_example"
    assert result.expires_at == datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer app.jwt.value"
    assert sent.headers["Accept"] == "application/vnd.github+json"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 422, 500])
async def test_refused_token_raises_without_leaking_credentials(respx_mock, status):
    respx_mock.post(TOKEN_URL).respond(status, json={"message": "nope"})

    async with httpx.AsyncClient() as client:
        with pytest.raises(GitHubAuthError) as error:
            await get_installation_token(client, "secret.jwt.value", INSTALLATION_ID)

    assert str(status) in str(error.value)
    assert "secret.jwt.value" not in str(error.value)


@pytest.mark.anyio
async def test_installation_token_is_hidden_when_printed(respx_mock):
    respx_mock.post(TOKEN_URL).respond(
        201, json={"token": "ghs_example", "expires_at": "2026-11-04T12:00:00Z"}
    )

    async with httpx.AsyncClient() as client:
        result = await get_installation_token(client, "app.jwt.value", INSTALLATION_ID)

    assert "ghs_example" not in repr(result)
