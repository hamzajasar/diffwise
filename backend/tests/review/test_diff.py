from pathlib import Path

import pytest

from app.review.diff import ChangedFile, DiffParseError, parse_diff

# Real diffs: one downloaded from GitHub, the rest produced by `git diff` for each edge case.
DIFFS = Path(__file__).parent.parent / "fixtures" / "diffs"


def load(name: str) -> str:
    return (DIFFS / name).read_text()


def test_new_file_from_github():
    assert parse_diff(load("github_new_file.diff")) == [
        ChangedFile(
            path="greet.py",
            added_lines={1: "def greet(name: str) -> str:", 2: '    return f"Hello, {name}!"'},
        )
    ]


def test_multiple_hunks_use_new_file_line_numbers():
    [changed] = parse_diff(load("multiple_hunks.diff"))

    assert changed.path == "multi.py"
    # Line 26 only exists because line 25 grew: numbers come from the *new* file.
    assert changed.added_lines == {
        3: "line 3 changed",
        25: "line 25 changed",
        26: "line 25b added",
    }


def test_renamed_and_modified_file_uses_the_new_path():
    [changed] = parse_diff(load("renamed_and_modified.diff"))

    assert changed.path == "after_name.py"
    assert list(changed.added_lines) == [6, 7, 8, 9]


def test_no_newline_marker_is_not_treated_as_a_line():
    [changed] = parse_diff(load("no_newline_at_eof.diff"))

    assert changed.added_lines == {1: "x = 2"}


@pytest.mark.parametrize(
    "name",
    [
        "deleted_file.diff",
        "rename_only.diff",
        "only_removed_lines.diff",
        "binary_file.diff",
    ],
)
def test_files_without_added_lines_are_skipped(name):
    assert parse_diff(load(name)) == []


def test_several_files_keep_diff_order_and_skip_unchanged_ones():
    names = ["multiple_hunks.diff", "deleted_file.diff", "github_new_file.diff"]
    combined = "".join(load(name) for name in names)

    assert [f.path for f in parse_diff(combined)] == ["multi.py", "greet.py"]


@pytest.mark.parametrize("text", ["", "this is not a diff\n"])
def test_empty_or_non_diff_text_gives_no_files(text):
    assert parse_diff(text) == []


def test_truncated_diff_raises():
    # The hunk header promises 5 lines but only 2 follow (e.g. a cut-off download).
    truncated = "--- a/x.py\n+++ b/x.py\n@@ -1,5 +1,5 @@\n-a\n+b\n"

    with pytest.raises(DiffParseError):
        parse_diff(truncated)


def test_windows_line_endings_are_stripped():
    [changed] = parse_diff(load("github_new_file.diff").replace("\n", "\r\n"))

    assert changed.added_lines[1] == "def greet(name: str) -> str:"


def test_large_diff_keeps_every_line():
    count = 5000
    body = "".join(f"+value_{n} = {n}\n" for n in range(1, count + 1))
    diff = f"--- /dev/null\n+++ b/big.py\n@@ -0,0 +1,{count} @@\n{body}"

    [changed] = parse_diff(diff)

    assert len(changed.added_lines) == count
    assert changed.added_lines[1] == "value_1 = 1"
    assert changed.added_lines[count] == f"value_{count} = {count}"
