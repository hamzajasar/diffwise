"""Read pull request data from the GitHub API."""

import re
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.github.auth import GITHUB_API, GITHUB_HEADERS

# "owner/repo": letters, digits, ".", "-", "_" only. Checked before the value goes
# into a URL path, so a crafted name like "../../admin" can't reach another endpoint.
REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# A full commit SHA: 40 hex characters (SHA-1), or 64 for repositories using SHA-256.
COMMIT_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# Bigger files are almost always generated or vendored; skip them instead of loading them.
MAX_FILE_BYTES = 1_000_000


class GitHubAPIError(Exception):
    """A GitHub API call failed."""


def auth_headers(token: SecretStr, accept: str) -> dict[str, str]:
    return {
        **GITHUB_HEADERS,
        "Accept": accept,
        "Authorization": f"Bearer {token.get_secret_value()}",
    }


def check_repo(repo: str) -> None:
    if not REPO_NAME.fullmatch(repo) or ".." in repo:
        raise ValueError(f"Invalid repository name: {repo!r}")


async def fetch_pr_diff(
    client: httpx.AsyncClient, token: SecretStr, repo: str, pr_number: int
) -> str:
    """Return the pull request's changes as a unified diff."""
    check_repo(repo)
    if pr_number < 1:
        raise ValueError(f"Invalid pull request number: {pr_number}")

    response = await client.get(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=auth_headers(token, "application/vnd.github.diff"),  # the diff, not JSON
    )
    if response.status_code != httpx.codes.OK:
        # Status code only: never echo the token or response body into errors/logs.
        raise GitHubAPIError(f"Could not fetch the diff (HTTP {response.status_code})")
    return response.text


async def fetch_file(
    client: httpx.AsyncClient, token: SecretStr, repo: str, path: str, ref: str
) -> str | None:
    """Return a file's text at commit `ref`, or None if it's too large or not UTF-8 text."""
    check_repo(repo)
    parts = path.split("/")
    if not path or path.startswith("/") or ".." in parts or "" in parts:
        raise ValueError(f"Invalid file path: {path!r}")
    if not COMMIT_SHA.fullmatch(ref):
        raise ValueError(f"Invalid commit SHA: {ref!r}")

    response = await client.get(
        f"{GITHUB_API}/repos/{repo}/contents/{quote(path)}",  # e.g. "my file.py" -> "my%20file.py"
        params={"ref": ref},
        headers=auth_headers(token, "application/vnd.github.raw"),  # the file itself, not JSON
    )
    if response.status_code != httpx.codes.OK:
        raise GitHubAPIError(f"Could not fetch {path} (HTTP {response.status_code})")
    if len(response.content) > MAX_FILE_BYTES:
        return None
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:  # binary file (image, archive...): nothing for linters to read
        return None


async def fetch_files(
    client: httpx.AsyncClient, token: SecretStr, repo: str, paths: list[str], ref: str
) -> dict[str, str]:
    """Fetch several files at `ref`; files that are skipped (too large, binary) are left out."""
    files = {}
    for path in paths:
        text = await fetch_file(client, token, repo, path, ref)
        if text is not None:
            files[path] = text
    return files
