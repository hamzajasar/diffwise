import httpx
import pytest
from pydantic import SecretStr

from app.github.auth import GITHUB_API
from app.github.pulls import GitHubAPIError, fetch_pr_diff

REPO = "hamzajasar/diffwise-playground"
TOKEN = SecretStr("ghs_test_token")
DIFF = "--- /dev/null\n+++ b/greet.py\n@@ -0,0 +1 @@\n+print('hi')\n"


async def fetch(repo: str = REPO, pr_number: int = 1) -> str:
    async with httpx.AsyncClient() as client:
        return await fetch_pr_diff(client, TOKEN, repo, pr_number)


@pytest.mark.anyio
async def test_fetches_the_diff_with_the_installation_token(respx_mock):
    route = respx_mock.get(f"{GITHUB_API}/repos/{REPO}/pulls/1").respond(200, text=DIFF)

    assert await fetch() == DIFF
    sent = route.calls.last.request
    assert sent.headers["Accept"] == "application/vnd.github.diff"
    assert sent.headers["Authorization"] == "Bearer ghs_test_token"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 406, 500])
async def test_failed_request_raises_without_leaking_the_token(respx_mock, status):
    # 406 is what GitHub returns when a diff is too large to generate.
    respx_mock.get(f"{GITHUB_API}/repos/{REPO}/pulls/1").respond(status, text="error")

    with pytest.raises(GitHubAPIError) as error:
        await fetch()

    assert str(status) in str(error.value)
    assert "ghs_test_token" not in str(error.value)


@pytest.mark.anyio
async def test_unusual_but_valid_repo_name_is_accepted(respx_mock):
    repo = "my-org.io/repo_name.v2"
    respx_mock.get(f"{GITHUB_API}/repos/{repo}/pulls/7").respond(200, text=DIFF)

    assert await fetch(repo, 7) == DIFF


@pytest.mark.anyio
@pytest.mark.parametrize(
    "repo",
    [
        "",
        "owner",  # no repo part
        "owner/repo/extra",  # extra path segment
        "../../admin",  # path traversal
        "owner/..",
        "own er/repo",  # whitespace
        "owner/repo?per_page=1",  # query injection
    ],
)
async def test_invalid_repo_name_is_rejected_before_any_request(respx_mock, repo):
    with pytest.raises(ValueError):
        await fetch(repo=repo)

    assert respx_mock.calls.call_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize("pr_number", [0, -1])
async def test_invalid_pr_number_is_rejected(respx_mock, pr_number):
    with pytest.raises(ValueError):
        await fetch(pr_number=pr_number)

    assert respx_mock.calls.call_count == 0
