"""CHANGELOG.md, read and written as the release's source of record.

Notes go under `## Unreleased`, and the release retitles that section to
`## <version>` and publishes its content — so the file and the release say one
thing, and neither is composed in a form field nobody reviews.

Writing them is part of releasing rather than a per-change chore. The bump level
can't be chosen without reading what landed, and that reading is what produces the
notes; splitting the two means deciding the version with the reasoning forgotten.
Nothing here enforces when they're written, only that the section says something
by the time a release reads it.

That direction is the whole point. The release body used to be authored outside
the repo and proxied inward, which made it the source: nothing constrained its
shape, and across the suite it took at least three incompatible forms, each now
permanent in some changelog. Reading the notes out of the file instead makes a
duplicated or mismatched heading unreachable rather than a shape to tolerate —
shipyard writes the only `## <version>` heading there is.
"""
from __future__ import annotations

import pathlib
import re

from ._common import plugin_root

UNRELEASED = re.compile(r"^##\s+\[?unreleased\]?\s*$", re.IGNORECASE)


def _staged_index(lines: list[str]) -> int | None:
    """Index of a leading `## Unreleased` heading, or None when the first
    section is anything else."""
    for i, line in enumerate(lines):
        if line.startswith("## "):
            return i if UNRELEASED.match(line) else None
    return None


def _section_end(lines: list[str], start: int) -> int:
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            return i
    return len(lines)


def _changelog(root: str | pathlib.Path | None) -> pathlib.Path:
    path = plugin_root(root) / "CHANGELOG.md"
    if not path.exists():
        raise SystemExit(
            f"shipyard: no CHANGELOG.md at {path}. It is the source the release "
            "notes are read from, so there is nothing to release without it.")
    return path


def staged(root: str | pathlib.Path | None = None) -> str:
    """The content of the leading `## Unreleased` section.

    A release reads its notes from here rather than taking them from whoever
    published it, which is what stops the same notes existing in two wordings.
    No section, or an empty one, is a failed release and not a release with empty
    notes: the alternative is publishing a version whose changelog entry says
    nothing, which cannot be fixed afterwards without moving a tag."""
    path = _changelog(root)
    lines = path.read_text().splitlines()
    idx = _staged_index(lines)
    if idx is None:
        raise SystemExit(
            f"shipyard: {path} has no leading `## Unreleased` section. Write the "
            "notes for this release there first — reading what landed is also how "
            "you pick the bump.")
    body = "\n".join(lines[idx + 1:_section_end(lines, idx)]).strip()
    if not body:
        raise SystemExit(
            f"shipyard: {path}'s `## Unreleased` section is empty. Write what "
            "changed before releasing it.")
    return body


def section(version: str, root: str | pathlib.Path | None = None) -> str:
    """A released version's section, for publishing as the release body.

    The same boundaries the writer computes, read in the other direction, so the
    published body and the committed section cannot say different things."""
    path = _changelog(root)
    lines = path.read_text().splitlines()
    header = f"## {version}"
    idx = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if idx is None:
        raise SystemExit(f"shipyard: {path} has no {header} section.")
    return "\n".join(lines[idx + 1:_section_end(lines, idx)]).strip()


def retitle(version: str, root: str | pathlib.Path | None = None) -> str:
    """Rename the staged `## Unreleased` section to `## <version>` in place.

    Returns the section body, so the caller publishes exactly what it committed.
    Nothing is prepended and no heading is taken from outside this file, which is
    what makes a duplicated or mismatched heading unreachable rather than
    something the parser has to tolerate."""
    path = _changelog(root)
    body = staged(root)
    header = f"## {version}"
    text = path.read_text()
    if header in text:
        raise SystemExit(
            f"shipyard: {path} already has a {header} section. Releasing "
            f"{version} twice would leave two.")
    lines = text.splitlines()
    idx = _staged_index(lines)
    lines[idx] = header
    path.write_text("\n".join(lines).rstrip() + "\n")
    return body
