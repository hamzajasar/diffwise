import subprocess
from pathlib import Path

import pytest

from app.review import static_analysis
from app.review.diff import ChangedFile
from app.review.findings import Category, Severity
from app.review.static_analysis import AnalysisError, analyze

# Deliberately vulnerable code (".txt" so our own linters and pytest leave it alone).
FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE = (FIXTURES / "code" / "vulnerable_sample.py.txt").read_text()
PATH = "pkg/vulnerable.py"


def all_lines_added(path: str, text: str) -> list[ChangedFile]:
    """The diff of a brand-new file: every line is added."""
    return [ChangedFile(path, {n: line for n, line in enumerate(text.splitlines(), 1)})]


def rules(findings) -> set[tuple[int, str]]:
    return {(f.line, f.rule) for f in findings}


def test_finds_bugs_and_security_issues_in_a_new_file():
    findings = analyze({PATH: SAMPLE}, all_lines_added(PATH, SAMPLE))

    assert rules(findings) == {
        (1, "F401"),  # unused import
        (4, "B105"),  # hard-coded password
        (8, "B608"),  # SQL injection
        (13, "B602"),  # subprocess with shell=True
        (16, "B006"),  # mutable default argument
        (22, "F821"),  # undefined name
    }
    assert all(f.path == PATH for f in findings)


def test_import_only_noise_is_filtered_out():
    # Bandit flags `import subprocess` (B404) on line 2; that's not worth a review comment.
    findings = analyze({PATH: SAMPLE}, all_lines_added(PATH, SAMPLE))

    assert "B404" not in {f.rule for f in findings}


@pytest.mark.parametrize(
    ("rule", "severity", "category"),
    [
        ("B602", Severity.HIGH, Category.SECURITY),
        ("B608", Severity.MEDIUM, Category.SECURITY),
        ("B105", Severity.LOW, Category.SECURITY),
        ("F401", Severity.MEDIUM, Category.BUG),
    ],
)
def test_severity_and_category_mapping(rule, severity, category):
    findings = {f.rule: f for f in analyze({PATH: SAMPLE}, all_lines_added(PATH, SAMPLE))}

    assert findings[rule].severity == severity
    assert findings[rule].category == category


def test_only_findings_on_added_lines_are_kept():
    lines = SAMPLE.splitlines()
    changed = [ChangedFile(PATH, {13: lines[12]})]  # the PR only added line 13

    assert rules(analyze({PATH: SAMPLE}, changed)) == {(13, "B602")}


def test_findings_in_unchanged_files_are_ignored():
    # The file is analyzed but isn't part of the diff at all.
    assert analyze({PATH: SAMPLE}, []) == []


def test_syntax_error_is_reported_once_as_high_severity():
    broken = "def oops(:\n    return 1\n"

    findings = analyze({"bad.py": broken}, all_lines_added("bad.py", broken))

    assert [(f.line, f.rule, f.severity) for f in findings] == [
        (1, "invalid-syntax", Severity.HIGH)
    ]


def test_clean_code_has_no_findings():
    clean = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'

    assert analyze({"greet.py": clean}, all_lines_added("greet.py", clean)) == []


def test_non_python_files_are_skipped_without_running_tools(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no tool should run")

    monkeypatch.setattr(static_analysis.subprocess, "run", fail)
    text = 'password = "hunter2"\n'

    assert analyze({"config.yml": text}, all_lines_added("config.yml", text)) == []


def test_analyzed_code_is_never_executed(tmp_path):
    marker = tmp_path / "pwned"
    malicious = f"open({str(marker)!r}, 'w').write('ran')\n"

    analyze({"evil.py": malicious}, all_lines_added("evil.py", malicious))

    assert not marker.exists()


@pytest.mark.parametrize("path", ["../escape.py", "/etc/evil.py", "pkg/../../escape.py"])
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValueError):
        analyze({path: "x = 1\n"}, [])


def fake_tool(returncode: int, stdout: str):
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    return run


@pytest.mark.parametrize(
    "run",
    [
        fake_tool(2, "[]"),  # tool crashed / bad usage
        fake_tool(0, "not json"),  # unreadable output
    ],
)
def test_tool_failures_raise_analysis_error(monkeypatch, run):
    monkeypatch.setattr(static_analysis.subprocess, "run", run)

    with pytest.raises(AnalysisError):
        analyze({"a.py": "x = 1\n"}, all_lines_added("a.py", "x = 1\n"))


def test_tool_timeout_raises_analysis_error(monkeypatch):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=60)

    monkeypatch.setattr(static_analysis.subprocess, "run", slow)

    with pytest.raises(AnalysisError):
        analyze({"a.py": "x = 1\n"}, all_lines_added("a.py", "x = 1\n"))
