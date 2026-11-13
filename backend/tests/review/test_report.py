import pytest

from app.review import report
from app.review.findings import Category, Finding, Severity
from app.review.report import ZERO_WIDTH_SPACE, build_review


def finding(line=1, severity=Severity.MEDIUM, path="app.py", message="Problem", rule="F401"):
    return Finding(
        path=path,
        line=line,
        severity=severity,
        category=Category.BUG,
        rule=rule,
        message=message,
        source="ruff",
    )


def test_no_findings_gives_a_friendly_summary_and_no_comments():
    review = build_review([])

    assert "no issues" in review.body
    assert review.comments == []


def test_summary_counts_findings_by_severity():
    findings = [finding(1, Severity.HIGH), finding(2), finding(3), finding(4, Severity.LOW)]

    body = build_review(findings).body

    assert "4 issues" in body
    assert "1 high, 2 medium, 1 low" in body


def test_single_finding_uses_singular_wording():
    assert "1 issue " in build_review([finding()]).body


def test_comments_are_ordered_most_severe_first():
    findings = [
        finding(9, Severity.LOW),
        finding(5, Severity.MEDIUM),
        finding(7, Severity.HIGH),
    ]

    assert [c.line for c in build_review(findings).comments] == [7, 5, 9]


def test_comment_shows_severity_category_rule_and_message():
    comment = build_review(
        [finding(13, Severity.HIGH, rule="B602", message="shell=True")]
    ).comments[0]

    assert (comment.path, comment.line) == ("app.py", 13)
    assert "high · bug" in comment.body
    assert "`B602`" in comment.body
    assert "shell=True" in comment.body


def test_mentions_from_analyzed_code_are_neutralized():
    # e.g. Bandit quoting `PASSWORD = "@everyone"` from the pull request
    message = "Possible hardcoded password: '@everyone'"
    comment = build_review([finding(message=message)]).comments[0]

    assert "@everyone" not in comment.body
    assert f"@{ZERO_WIDTH_SPACE}everyone" in comment.body


def test_long_messages_are_truncated(monkeypatch):
    monkeypatch.setattr(report, "MAX_MESSAGE_CHARS", 10)

    body = build_review([finding(message="x" * 50)]).comments[0].body

    assert "x" * 9 + "…" in body
    assert "x" * 10 not in body


@pytest.mark.parametrize(("count", "shown", "hidden"), [(3, 3, 0), (4, 3, 1), (10, 3, 7)])
def test_comment_count_is_capped_most_severe_kept(monkeypatch, count, shown, hidden):
    monkeypatch.setattr(report, "MAX_COMMENTS", 3)
    findings = [finding(n, Severity.LOW) for n in range(1, count)] + [finding(99, Severity.HIGH)]

    review = build_review(findings)

    assert len(review.comments) == shown
    assert review.comments[0].line == 99  # the high-severity one survives the cap
    assert (f"{hidden} more not shown" in review.body) == bool(hidden)
