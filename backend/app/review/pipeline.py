"""Review one pull request from start to finish: GitHub data in, findings out."""

import asyncio

import httpx

from app.config import Settings
from app.github.auth import create_app_jwt, get_installation_token
from app.github.events import PullRequestEvent
from app.github.pulls import fetch_files, fetch_pr_diff
from app.review.diff import parse_diff
from app.review.findings import Finding
from app.review.static_analysis import analyze


async def review_pull_request(
    client: httpx.AsyncClient, settings: Settings, event: PullRequestEvent
) -> list[Finding]:
    # 1. Authenticate as the app, for this installation only.
    app_jwt = create_app_jwt(settings.github_app_id, settings.github_private_key_path.read_text())
    token = (await get_installation_token(client, app_jwt, event.installation_id)).token

    # 2-3. What changed, and on which new lines.
    changed_files = parse_diff(await fetch_pr_diff(client, token, event.repo, event.number))

    # 4. Linters need whole files; only download the Python files that gained lines.
    python_paths = [f.path for f in changed_files if f.path.endswith(".py")]
    files = await fetch_files(client, token, event.repo, python_paths, event.head_sha)

    # 5. Ruff and Bandit block while they run, so keep them off the event loop.
    return await asyncio.to_thread(analyze, files, changed_files)
