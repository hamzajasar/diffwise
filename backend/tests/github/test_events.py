import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.github.events import PullRequestEvent

FIXTURE = Path(__file__).parent.parent / "fixtures" / "github" / "pull_request_opened.json"
PAYLOAD = json.loads(FIXTURE.read_text())  # real webhook sent by GitHub


def event(**changes) -> PullRequestEvent:
    """The real payload with some fields changed, e.g. event(action="closed")."""
    payload = copy.deepcopy(PAYLOAD)
    if "action" in changes:
        payload["action"] = changes["action"]
    if "draft" in changes:
        payload["pull_request"]["draft"] = changes["draft"]
    return PullRequestEvent.model_validate(payload)


def test_reads_the_fields_we_need_from_a_real_webhook():
    e = event()

    assert (e.action, e.number, e.repo) == ("opened", 1, "hamzajasar/diffwise-playground")
    assert e.installation_id == 178198846
    assert e.head_sha == "04be381ad1ed7f29cd0ba6046e33a4842894dd90"


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "ready_for_review"])
def test_actions_that_change_code_are_reviewed(action):
    assert event(action=action).should_review


@pytest.mark.parametrize(
    "action", ["closed", "edited", "labeled", "assigned", "converted_to_draft"]
)
def test_other_actions_are_not_reviewed(action):
    assert not event(action=action).should_review


def test_draft_pull_requests_are_not_reviewed():
    assert not event(draft=True).should_review


def invalid(path: list[str], value) -> dict:
    payload = copy.deepcopy(PAYLOAD)
    target = payload
    for key in path[:-1]:
        target = target[key]
    if value is ...:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        invalid(["installation"], ...),  # app not installed / wrong event type
        invalid(["number"], 0),
        invalid(["repository", "full_name"], "../../admin"),
        invalid(["repository", "full_name"], "owner/repo?x=1"),
        invalid(["pull_request", "head", "sha"], "main"),
        invalid(["pull_request", "head", "sha"], "04be381"),  # abbreviated SHA
    ],
)
def test_malformed_payloads_are_rejected(payload):
    with pytest.raises(ValidationError):
        PullRequestEvent.model_validate(payload)
