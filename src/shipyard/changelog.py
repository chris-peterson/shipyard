"""Write a release section into CHANGELOG.md from a GitHub Release body.

Run by the release workflow on `release: published`. Reads VERSION (e.g.
"0.10.1") and BODY (the release-notes markdown) from the environment and puts a
`## <VERSION>` section directly under the top-level `# Changelog` title.

Contributors commonly stage notes under a `## Unreleased` heading as they land
work. When that section is present it *becomes* the `## <VERSION>` section —
retitled in place — so the release doesn't land a second copy of the same notes
beside a heading that then goes stale. The release body is what was published,
so it wins the section content; the staged text is echoed to stderr when it
differs, and kept when the release body is empty.

Idempotent: an existing `## <VERSION>` section leaves the file unchanged, so
re-publishing a release doesn't duplicate the entry.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

from ._common import plugin_root

UNRELEASED = re.compile(r"^##\s+\[?unreleased\]?\s*$", re.IGNORECASE)


def _warn(message: str) -> None:
    sys.stderr.write(f"shipyard changelog: {message}\n")


def _section(header: str, body: str) -> list[str]:
    return [header, ""] + ([body, ""] if body else [])


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


def _normalized(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.splitlines() if line.strip())


def _reconcile(staged: str, body: str) -> str:
    if not body:
        _warn("release body is empty; keeping the staged ## Unreleased notes.")
        return staged
    if staged and _normalized(staged) != _normalized(body):
        _warn("release body differs from the staged ## Unreleased notes; using the "
              "release body. The staged text was:\n" + staged)
    return body


def run(root: str | pathlib.Path | None = None) -> int:
    version = os.environ["VERSION"].strip()
    body = os.environ.get("BODY", "").strip()
    changelog = plugin_root(root) / "CHANGELOG.md"

    text = changelog.read_text()
    header = f"## {version}"
    if header in text:
        _warn(f"CHANGELOG.md already has a {header} section; leaving unchanged.")
        return 0

    lines = text.splitlines()
    try:
        title_idx = next(i for i, line in enumerate(lines) if line.startswith("# "))
    except StopIteration:
        raise SystemExit("CHANGELOG.md has no top-level '# ' title.")

    title = lines[: title_idx + 1]
    rest = lines[title_idx + 1 :]
    while rest and not rest[0].strip():
        rest.pop(0)

    staged_idx = _staged_index(rest)
    if staged_idx is None:
        rest = _section(header, body) + rest
    else:
        end = _section_end(rest, staged_idx)
        staged = "\n".join(rest[staged_idx + 1 : end]).strip()
        rest = (rest[:staged_idx]
                + _section(header, _reconcile(staged, body))
                + rest[end:])

    changelog.write_text("\n".join(title + [""] + rest).rstrip() + "\n")
    return 0
