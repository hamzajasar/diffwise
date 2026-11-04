"""Read pull request data from the GitHub API."""

import re

import httpx
from pydantic import SecretStr

from app.github.auth import GITHUB_API, GITHUB_HEADERS

# "owner/repo": letters, digits, ".", "-", "_" only. Checked before the value goes
# into a URL path, so a crafted name like "../../admin" can't reach another endpoint.
REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class GitHubAPIError(Exception):
    """A GitHub API call failed."""


async def fetch_pr_diff(
    client: httpx.AsyncClient, token: SecretStr, repo: str, pr_number: int
) -> str:
    """Return the pull request's changes as a unified diff."""
    if not REPO_NAME.fullmatch(repo) or ".." in repo:
        raise ValueError(f"Invalid repository name: {repo!r}")
    if pr_number < 1:
        raise ValueError(f"Invalid pull request number: {pr_number}")

    response = await client.get(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers={
            **GITHUB_HEADERS,
            "Accept": "application/vnd.github.diff",  # ask for the diff, not JSON
            "Authorization": f"Bearer {token.get_secret_value()}",
        },
    )
    if response.status_code != httpx.codes.OK:
        # Status code only: never echo the token or response body into errors/logs.
        raise GitHubAPIError(f"Could not fetch the diff (HTTP {response.status_code})")
    return response.text
