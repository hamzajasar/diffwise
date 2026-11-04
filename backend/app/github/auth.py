"""Authenticate as the GitHub App.

Two steps, both required by GitHub:
1. Prove we are the app: sign a short-lived JWT with the app's private key (RS256).
2. Exchange that JWT for an installation access token, which works for 1 hour and only on
   the repositories where the app is installed, with only the permissions it was granted.
"""

import time
from datetime import datetime

import httpx
import jwt
from pydantic import BaseModel, SecretStr

GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

# GitHub rejects JWTs that live longer than 10 minutes, and ones "issued in the future".
# Backdating `iat` absorbs small clock differences between our machine and GitHub's.
CLOCK_SKEW_SECONDS = 60
JWT_LIFETIME_SECONDS = 9 * 60


class GitHubAuthError(Exception):
    """GitHub refused to authenticate the app (bad key, wrong app ID, app not installed...)."""


class InstallationToken(BaseModel):
    token: SecretStr  # masked if printed or logged
    expires_at: datetime


def create_app_jwt(app_id: int, private_key: str, now: int | None = None) -> str:
    """Return a JWT that proves to GitHub we are this app. `now` is injectable for tests."""
    now = int(time.time()) if now is None else now
    claims = {
        "iat": now - CLOCK_SKEW_SECONDS,  # issued at
        "exp": now + JWT_LIFETIME_SECONDS,  # expires at
        "iss": str(app_id),  # issuer: which app this is
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


async def get_installation_token(
    client: httpx.AsyncClient, app_jwt: str, installation_id: int
) -> InstallationToken:
    """Exchange the app JWT for a token scoped to one installation."""
    response = await client.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={**GITHUB_HEADERS, "Authorization": f"Bearer {app_jwt}"},
    )
    if response.status_code != httpx.codes.CREATED:
        # Status code only: the response and request may contain credentials.
        raise GitHubAuthError(
            f"GitHub refused the installation token (HTTP {response.status_code})"
        )
    return InstallationToken.model_validate(response.json())
