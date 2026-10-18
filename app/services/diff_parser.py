"""Parse unified diffs to extract changed-line positions for GitHub review comments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
BINARY_RE = re.compile(r"^Binary files .+ differ$")

SKIP_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".bmp", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyc", ".class", ".o", ".obj",
    ".lock",
})


@dataclass
class FileDiff:
    path: str
    patch: str
    added_lines: dict[int, int] = field(default_factory=dict)
    # added_lines maps new-file line number -> diff position (1-based position in the diff hunk)


def is_binary_or_skipped(path: str, patch: str) -> bool:
    if any(path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return True
    return bool(BINARY_RE.search(patch))


def parse_patch(patch: str) -> dict[int, int]:
    """Return {new_file_line: diff_position} for added/modified lines."""
    result: dict[int, int] = {}
    position = 0
    current_line = 0

    for raw_line in patch.split("\n"):
        m = HUNK_RE.match(raw_line)
        if m:
            current_line = int(m.group(1))
            position += 1
            continue

        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue

        if not raw_line and position == 0:
            continue

        position += 1

        if raw_line.startswith("+"):
            result[current_line] = position
            current_line += 1
        elif raw_line.startswith("-"):
            pass  # deleted line: don't advance new-file line counter
        else:
            current_line += 1  # context line

    return result


def parse_pr_files(files_data: list[dict]) -> list[FileDiff]:
    """Parse GitHub API file objects into FileDiff list."""
    diffs: list[FileDiff] = []
    for f in files_data:
        path = f.get("filename", "")
        patch = f.get("patch", "")
        status = f.get("status", "")

        if status == "removed" or not patch:
            continue
        if is_binary_or_skipped(path, patch):
            continue

        added_lines = parse_patch(patch)
        diffs.append(FileDiff(path=path, patch=patch, added_lines=added_lines))

    return diffs
