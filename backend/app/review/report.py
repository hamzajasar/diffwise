"""Turn findings into the text of a pull request review (no network here)."""

from collections import Counter
from dataclasses import dataclass

from app.review.findings import Finding, Severity

MAX_COMMENTS = 50  # keep huge pull requests readable
MAX_MESSAGE_CHARS = 500

SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
SEVERITY_MARK = {Severity.HIGH: "🔴", Severity.MEDIUM: "🟠", Severity.LOW: "🟡"}

# A zero-width space after "@" keeps the text readable but stops GitHub from treating it as a
# mention, so code in a pull request (e.g. PASSWORD = "@someone") can't make the bot ping people.
ZERO_WIDTH_SPACE = "​"


@dataclass(frozen=True)
class ReviewComment:
    path: str
    line: int
    body: str


@dataclass(frozen=True)
class Review:
    body: str
    comments: list[ReviewComment]


def build_review(findings: list[Finding]) -> Review:
    ordered = sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.path, f.line))
    shown = ordered[:MAX_COMMENTS]
    comments = [ReviewComment(f.path, f.line, _comment_body(f)) for f in shown]
    return Review(body=_summary(findings, hidden=len(ordered) - len(shown)), comments=comments)


def _summary(findings: list[Finding], hidden: int) -> str:
    footer = "\n\n<sub>Static analysis by diffwise (Ruff, Bandit) on the lines this PR adds.</sub>"
    if not findings:
        return "✅ **diffwise found no issues in the changed lines.**" + footer
    counts = Counter(f.severity for f in findings)
    breakdown = ", ".join(f"{counts[s]} {s}" for s in SEVERITY_ORDER if counts[s])
    noun = "issue" if len(findings) == 1 else "issues"
    text = f"**diffwise found {len(findings)} {noun} in the changed lines:** {breakdown}."
    if hidden:
        text += f"\n\nShowing the {MAX_COMMENTS} most severe; {hidden} more not shown."
    return text + footer


def _comment_body(finding: Finding) -> str:
    message = finding.message
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[: MAX_MESSAGE_CHARS - 1] + "…"
    header = (
        f"{SEVERITY_MARK[finding.severity]} **{finding.severity} · {finding.category}** "
        f"· `{finding.rule}` ({finding.source})"
    )
    return _no_mentions(f"{header}\n\n{message}")


def _no_mentions(text: str) -> str:
    return text.replace("@", "@" + ZERO_WIDTH_SPACE)
