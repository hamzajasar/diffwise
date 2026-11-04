"""Turn a unified diff into the lines a review can comment on.

GitHub only accepts review comments on lines that are part of the diff. We review the
*new* version of the code, so what matters is each file's added lines and their line
numbers in the new file.
"""

from dataclasses import dataclass

from unidiff import PatchSet, UnidiffParseError


class DiffParseError(ValueError):
    """The diff is corrupted (e.g. truncated), so it can't be trusted."""


@dataclass(frozen=True)
class ChangedFile:
    path: str  # path in the new version (the new name, for renamed files)
    added_lines: dict[int, str]  # new-file line number -> line content


def parse_diff(diff_text: str) -> list[ChangedFile]:
    """Return every file with added lines, in diff order.

    Skipped, because there's nothing new to comment on: deleted files, pure renames,
    binary files, and files that only lost lines. Text that isn't a diff at all
    yields an empty list; a corrupted diff raises `DiffParseError`.
    """
    try:
        patch = PatchSet(diff_text)
    except UnidiffParseError as error:
        raise DiffParseError(f"Could not parse diff: {error}") from error

    changed_files = []
    for patched_file in patch:
        added_lines = {
            line.target_line_no: line.value.rstrip("\r\n")
            for hunk in patched_file
            for line in hunk
            if line.is_added
        }
        if added_lines:
            changed_files.append(ChangedFile(path=patched_file.path, added_lines=added_lines))
    return changed_files
