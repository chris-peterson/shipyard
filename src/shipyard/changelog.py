"""Prepend a release section to CHANGELOG.md from a GitHub Release body.

Run by the release workflow on `release: published`. Reads VERSION (e.g.
"0.10.1") and BODY (the release-notes markdown) from the environment and inserts
a `## <VERSION>` section directly under the top-level `# Changelog` title.
Idempotent: an existing `## <VERSION>` section leaves the file unchanged, so
re-publishing a release doesn't duplicate the entry.
"""
from __future__ import annotations

import os
import pathlib

from ._common import plugin_root


def run(root: str | pathlib.Path | None = None) -> int:
    version = os.environ["VERSION"].strip()
    body = os.environ.get("BODY", "").strip()
    changelog = plugin_root(root) / "CHANGELOG.md"

    text = changelog.read_text()
    header = f"## {version}"
    if header in text:
        import sys
        sys.stderr.write(f"CHANGELOG.md already has a {header} section; leaving unchanged.\n")
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

    section = [header, ""]
    if body:
        section += [body, ""]

    new_lines = title + [""] + section + rest
    changelog.write_text("\n".join(new_lines).rstrip() + "\n")
    return 0
