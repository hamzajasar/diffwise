import json

import httpx
import pytest
from pydantic import SecretStr

from app.github.auth import GITHUB_API
from app.github.pulls import GitHubAPIError
from app.github.reviews import post_review
from app.review.report import Review, ReviewComment

REPO = "hamzajasar/diffwise-playground"
SHA = "40d7025" + "0" * 33
TOKEN = SecretStr("ghs_test_token")
REVIEWS_URL = f"{GITHUB_API}/repos/{REPO}/pulls/2/reviews"
REVIEW = Review(body="summary", comments=[ReviewComment("app/users.py", 13, "🔴 high")])


async def post(repo=REPO, pr_number=2, sha=SHA, review=REVIEW) -> int:
    async with httpx.AsyncClient() as client:
        return await post_review(client, TOKEN, repo, pr_number, sha, review)


@pytest.mark.anyio
async def test_posts_a_comment_review_pinned_to_the_reviewed_commit(respx_mock):
    route = respx_mock.post(REVIEWS_URL).respond(200, json={"id": 42})

    assert await post() == 42
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer ghs_test_token"
    assert json.loads(sent.content) == {
        "commit_id": SHA,
        "event": "COMMENT",
        "body": "summary",
        "comments": [{"path": "app/users.py", "line": 13, "side": "RIGHT", "body": "🔴 high"}],
    }


@pytest.mark.anyio
async def test_review_without_comments_is_still_posted(respx_mock):
    route = respx_mock.post(REVIEWS_URL).respond(200, json={"id": 7})

    await post(review=Review(body="no issues", comments=[]))

    assert json.loads(route.calls.last.request.content)["comments"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 422, 500])
async def test_failed_post_raises_without_leaking_the_token(respx_mock, status):
    # 422 is what GitHub returns e.g. when a comment points at a line outside the diff.
    respx_mock.post(REVIEWS_URL).respond(status, json={"message": "nope"})

    with pytest.raises(GitHubAPIError) as error:
        await post()

    assert str(status) in str(error.value)
    assert "ghs_test_token" not in str(error.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"repo": "../../admin"},
        {"pr_number": 0},
        {"sha": "main"},
        {"sha": SHA[:39]},
    ],
)
async def test_invalid_input_is_rejected_before_any_request(respx_mock, kwargs):
    with pytest.raises(ValueError):
        await post(**kwargs)

    assert respx_mock.calls.call_count == 0
