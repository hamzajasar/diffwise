"""The parts of GitHub's `pull_request` webhook that diffwise needs, validated.

A webhook body is ~30 KB of JSON; we keep five fields and check their format before
anything else uses them (they end up in API URLs).
"""

from pydantic import BaseModel, Field

from app.github.pulls import COMMIT_SHA, REPO_NAME

# Actions that change the code under review. Others (closed, labeled, edited...) don't.
REVIEWABLE_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


class _Head(BaseModel):
    sha: str = Field(pattern=rf"^(?:{COMMIT_SHA.pattern})$")


class _PullRequest(BaseModel):
    head: _Head
    draft: bool = False


class _Repository(BaseModel):
    full_name: str = Field(pattern=rf"^(?:{REPO_NAME.pattern})$")


class _Installation(BaseModel):
    id: int = Field(gt=0)


class PullRequestEvent(BaseModel):
    action: str
    number: int = Field(gt=0)
    pull_request: _PullRequest
    repository: _Repository
    installation: _Installation

    @property
    def repo(self) -> str:
        return self.repository.full_name

    @property
    def head_sha(self) -> str:
        return self.pull_request.head.sha

    @property
    def installation_id(self) -> int:
        return self.installation.id

    @property
    def should_review(self) -> bool:
        """Review new or updated code, but not drafts (still work in progress)."""
        return self.action in REVIEWABLE_ACTIONS and not self.pull_request.draft
