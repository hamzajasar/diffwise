"""Static analysis of a pull request's changed Python files with Ruff (bugs) and Bandit (security).

Both tools only *read* the code; nothing from the pull request is ever executed. Files are
copied into a temporary folder, analyzed there, and only findings on added lines are kept.
"""

import json
import subprocess  # noqa: S404 - runs our own analysis tools with fixed arguments, never a shell
import sys
import tempfile
from pathlib import Path, PurePosixPath

from app.review.diff import ChangedFile
from app.review.findings import Category, Finding, Severity

TOOL_TIMEOUT_SECONDS = 60

# Ruff rule families that indicate real bugs: pyflakes (F), syntax errors (E9),
# bugbear (B) and pylint errors (PLE). Style rules are deliberately left out.
RUFF_RULES = "F,E9,B,PLE"
RUFF_HIGH_SEVERITY_PREFIXES = ("E9", "PLE", "invalid-syntax")

# Bandit checks that only flag *importing* a module (e.g. `import subprocess`): noise in a review.
BANDIT_IGNORED_TESTS = frozenset(
    {"B401", "B402", "B403", "B404", "B405", "B406", "B407", "B408", "B409", "B410", "B411", "B413"}
)


class AnalysisError(Exception):
    """An analysis tool failed to run (not: it found problems)."""


def analyze(files: dict[str, str], changed_files: list[ChangedFile]) -> list[Finding]:
    """Return findings for `files` (path -> content) that fall on lines added in the diff."""
    python_files = {path: text for path, text in files.items() if path.endswith(".py")}
    if not python_files:
        return []

    with tempfile.TemporaryDirectory(prefix="diffwise-") as tmp:
        root = Path(tmp).resolve()
        for path, text in python_files.items():
            target = _safe_target(root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        findings = _run_ruff(root) + _run_bandit(root)

    return _on_added_lines(findings, changed_files)


def _safe_target(root: Path, path: str) -> Path:
    """Map a repository path into `root`, refusing anything that could escape it."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError(f"Unsafe file path: {path!r}")
    target = (root / pure).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Unsafe file path: {path!r}")
    return target


def _run(tool_args: list[str], root: Path) -> str:
    """Run a Python-installed tool as `python -m <tool>` (no shell, fixed arguments)."""
    try:
        result = subprocess.run(  # noqa: S603 - arguments are ours; file paths stay inside `root`
            [sys.executable, "-m", *tool_args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AnalysisError(f"{tool_args[0]} timed out") from error
    # Exit code 1 means "problems found", which is the normal case for a review.
    if result.returncode not in (0, 1):
        raise AnalysisError(f"{tool_args[0]} failed (exit code {result.returncode})")
    return result.stdout


def _run_ruff(root: Path) -> list[Finding]:
    output = _run(
        ["ruff", "check", "--isolated", "--no-cache", "--select", RUFF_RULES,
         "--output-format", "json", "."],
        root,
    )  # fmt: skip
    findings = []
    for item in _parse_json(output, "ruff"):
        rule = item["code"]
        high = rule.startswith(RUFF_HIGH_SEVERITY_PREFIXES)
        findings.append(Finding(
            path=_relative(root, item["filename"]),
            line=item["location"]["row"],
            severity=Severity.HIGH if high else Severity.MEDIUM,
            category=Category.BUG,
            rule=rule,
            message=item["message"],
            source="ruff",
        ))  # fmt: skip
    return findings


def _run_bandit(root: Path) -> list[Finding]:
    # Files Bandit can't parse (syntax errors) are skipped by Bandit; Ruff reports those.
    report = _parse_json(_run(["bandit", "-q", "-f", "json", "-r", "."], root), "bandit")
    return [
        Finding(
            path=_relative(root, item["filename"]),
            line=item["line_number"],
            severity=Severity(item["issue_severity"].lower()),
            category=Category.SECURITY,
            rule=item["test_id"],
            message=item["issue_text"],
            source="bandit",
        )
        for item in report["results"]
        if item["test_id"] not in BANDIT_IGNORED_TESTS
    ]


def _parse_json(output: str, tool: str):
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise AnalysisError(f"{tool} returned invalid JSON") from error


def _relative(root: Path, filename: str) -> str:
    """Tools report absolute or ./-prefixed paths; turn them back into repository paths."""
    return (root / filename).resolve().relative_to(root).as_posix()


def _on_added_lines(findings: list[Finding], changed_files: list[ChangedFile]) -> list[Finding]:
    added = {(f.path, line) for f in changed_files for line in f.added_lines}
    kept = {(f.path, f.line, f.rule): f for f in findings if (f.path, f.line) in added}
    return sorted(kept.values(), key=lambda f: (f.path, f.line, f.rule))
