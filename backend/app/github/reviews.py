"""Post a review on a pull request."""

import httpx
from pydantic import SecretStr

from app.github.auth import GITHUB_API
from app.github.pulls import COMMIT_SHA, GitHubAPIError, auth_headers, check_repo
from app.review.report import Review


async def post_review(
    client: httpx.AsyncClient,
    token: SecretStr,
    repo: str,
    pr_number: int,
    commit_sha: str,
    review: Review,
) -> int:
    """Post `review` as a neutral COMMENT review on `commit_sha`; return the review's ID."""
    check_repo(repo)
    if pr_number < 1:
        raise ValueError(f"Invalid pull request number: {pr_number}")
    if not COMMIT_SHA.fullmatch(commit_sha):
        raise ValueError(f"Invalid commit SHA: {commit_sha!r}")

    response = await client.post(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews",
        headers=auth_headers(token, "application/vnd.github+json"),
        json={
            # Pin the review to the commit we analyzed, so line numbers match what we saw.
            "commit_id": commit_sha,
            # Inform, don't block: a bot shouldn't approve or request changes on its own.
            "event": "COMMENT",
            "body": review.body,
            "comments": [
                {"path": c.path, "line": c.line, "side": "RIGHT", "body": c.body}
                for c in review.comments
            ],
        },
    )
    if response.status_code != httpx.codes.OK:
        raise GitHubAPIError(f"Could not post the review (HTTP {response.status_code})")
    return response.json()["id"]
