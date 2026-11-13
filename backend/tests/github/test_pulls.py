import httpx
import pytest
from pydantic import SecretStr

from app.github import pulls
from app.github.auth import GITHUB_API
from app.github.pulls import GitHubAPIError, fetch_file, fetch_files, fetch_pr_diff

REPO = "hamzajasar/diffwise-playground"
TOKEN = SecretStr("ghs_test_token")
DIFF = "--- /dev/null\n+++ b/greet.py\n@@ -0,0 +1 @@\n+print('hi')\n"
HEAD = "04be381ad1ed7f29cd0ba6046e33a4842894dd90"  # real head SHA of playground PR #1
CONTENTS = f"{GITHUB_API}/repos/{REPO}/contents"


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


# --- Full file contents at the PR's head commit ---


async def get_file(path: str = "greet.py", ref: str = HEAD, repo: str = REPO) -> str | None:
    async with httpx.AsyncClient() as client:
        return await fetch_file(client, TOKEN, repo, path, ref)


@pytest.mark.anyio
async def test_fetches_raw_file_content_at_the_given_commit(respx_mock):
    route = respx_mock.get(f"{CONTENTS}/greet.py", params={"ref": HEAD}).respond(
        200, content=b"print('hi')\n"
    )

    assert await get_file() == "print('hi')\n"
    sent = route.calls.last.request
    assert sent.headers["Accept"] == "application/vnd.github.raw"
    assert sent.headers["Authorization"] == "Bearer ghs_test_token"


@pytest.mark.anyio
async def test_special_characters_in_paths_are_url_encoded(respx_mock):
    route = respx_mock.get(f"{CONTENTS}/src/my%20file%23v2.py").respond(200, content=b"x = 1\n")

    assert await get_file("src/my file#v2.py") == "x = 1\n"
    assert route.called


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 500])
async def test_failed_file_request_raises_without_leaking_the_token(respx_mock, status):
    respx_mock.get(f"{CONTENTS}/greet.py").respond(status)

    with pytest.raises(GitHubAPIError) as error:
        await get_file()

    assert str(status) in str(error.value)
    assert "ghs_test_token" not in str(error.value)


@pytest.mark.anyio
async def test_file_at_size_limit_is_returned(respx_mock, monkeypatch):
    monkeypatch.setattr(pulls, "MAX_FILE_BYTES", 10)
    respx_mock.get(f"{CONTENTS}/greet.py").respond(200, content=b"x" * 10)

    assert await get_file() == "x" * 10


@pytest.mark.anyio
async def test_file_over_size_limit_is_skipped(respx_mock, monkeypatch):
    monkeypatch.setattr(pulls, "MAX_FILE_BYTES", 10)
    respx_mock.get(f"{CONTENTS}/greet.py").respond(200, content=b"x" * 11)

    assert await get_file() is None


@pytest.mark.anyio
async def test_binary_file_is_skipped(respx_mock):
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe"
    respx_mock.get(f"{CONTENTS}/logo.png").respond(200, content=png_header)

    assert await get_file("logo.png") is None


@pytest.mark.anyio
async def test_non_ascii_utf8_text_is_kept(respx_mock):
    respx_mock.get(f"{CONTENTS}/greet.py").respond(200, content="name = 'Jašarević'\n".encode())

    assert await get_file() == "name = 'Jašarević'\n"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    ["", "/etc/passwd", "../secrets.py", "src/../../x.py", "src//x.py", "src/"],
)
async def test_invalid_paths_are_rejected_before_any_request(respx_mock, path):
    with pytest.raises(ValueError):
        await get_file(path)

    assert respx_mock.calls.call_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "ref",
    [
        "main",  # a branch name can move; we only accept exact commits
        HEAD[:39],  # one character short
        HEAD + "0",  # one character too long
        HEAD.upper(),  # GitHub SHAs are lowercase
        "g" * 40,  # not hexadecimal
        "../" + HEAD[3:],  # path trick
    ],
)
async def test_invalid_commit_sha_is_rejected_before_any_request(respx_mock, ref):
    with pytest.raises(ValueError):
        await get_file(ref=ref)

    assert respx_mock.calls.call_count == 0


@pytest.mark.anyio
async def test_sha256_commit_ids_are_accepted(respx_mock):
    sha256 = "a" * 64
    respx_mock.get(f"{CONTENTS}/greet.py", params={"ref": sha256}).respond(200, content=b"x\n")

    assert await get_file(ref=sha256) == "x\n"


@pytest.mark.anyio
async def test_fetch_files_leaves_out_skipped_files(respx_mock):
    respx_mock.get(f"{CONTENTS}/a.py").respond(200, content=b"a = 1\n")
    respx_mock.get(f"{CONTENTS}/logo.png").respond(200, content=b"\xff\xfe\x00binary")

    async with httpx.AsyncClient() as client:
        files = await fetch_files(client, TOKEN, REPO, ["a.py", "logo.png"], HEAD)

    assert files == {"a.py": "a = 1\n"}
