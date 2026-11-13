import json
from pathlib import Path

import httpx
import pytest

from app.github.auth import GITHUB_API, GitHubAuthError
from app.github.events import PullRequestEvent
from app.github.pulls import GitHubAPIError
from app.review.pipeline import review_pull_request

FIXTURES = Path(__file__).parent.parent / "fixtures"
EVENT = PullRequestEvent.model_validate(
    json.loads((FIXTURES / "github" / "pull_request_opened.json").read_text())
)
REPO_API = f"{GITHUB_API}/repos/{EVENT.repo}"
TOKEN_URL = f"{GITHUB_API}/app/installations/{EVENT.installation_id}/access_tokens"
SAMPLE = (FIXTURES / "code" / "vulnerable_sample.py.txt").read_text()


def new_file_diff(path: str, text: str) -> str:
    lines = text.splitlines()
    body = "".join(f"+{line}\n" for line in lines)
    return f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"


def fake_github(respx_mock, diff: str, files: dict[str, str]):
    respx_mock.post(TOKEN_URL).respond(
        201, json={"token": "ghs_fake", "expires_at": "2030-01-01T00:00:00Z"}
    )
    respx_mock.get(f"{REPO_API}/pulls/{EVENT.number}").respond(200, text=diff)
    for path, text in files.items():
        respx_mock.get(f"{REPO_API}/contents/{path}", params={"ref": EVENT.head_sha}).respond(
            200, content=text.encode()
        )


async def review(test_settings):
    async with httpx.AsyncClient() as client:
        return await review_pull_request(client, test_settings, EVENT)


@pytest.mark.anyio
async def test_reviews_a_pull_request_end_to_end(respx_mock, test_settings):
    fake_github(respx_mock, new_file_diff("app/vuln.py", SAMPLE), {"app/vuln.py": SAMPLE})

    findings = await review(test_settings)

    assert {(f.line, f.rule) for f in findings} == {
        (1, "F401"), (4, "B105"), (8, "B608"), (13, "B602"), (16, "B006"), (22, "F821"),
    }  # fmt: skip
    assert {f.path for f in findings} == {"app/vuln.py"}


@pytest.mark.anyio
async def test_non_python_changes_are_never_downloaded(respx_mock, test_settings):
    fake_github(respx_mock, new_file_diff("docs/notes.md", "password = hunter2\n"), {})

    assert await review(test_settings) == []
    assert not any("/contents/" in str(call.request.url) for call in respx_mock.calls)


@pytest.mark.anyio
async def test_authentication_failure_stops_before_reading_the_pull_request(
    respx_mock, test_settings
):
    respx_mock.post(TOKEN_URL).respond(401)
    diff_route = respx_mock.get(f"{REPO_API}/pulls/{EVENT.number}")

    with pytest.raises(GitHubAuthError):
        await review(test_settings)

    assert not diff_route.called


@pytest.mark.anyio
async def test_missing_pull_request_raises(respx_mock, test_settings):
    respx_mock.post(TOKEN_URL).respond(
        201, json={"token": "ghs_fake", "expires_at": "2030-01-01T00:00:00Z"}
    )
    respx_mock.get(f"{REPO_API}/pulls/{EVENT.number}").respond(404)

    with pytest.raises(GitHubAPIError):
        await review(test_settings)
