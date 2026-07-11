"""Render a plugin's docs/ from its sources, so there's no parallel doc artifact.

  skills/<name>/SKILL.md -> docs/skills/<name>.md   (YAML frontmatter stripped)
  rules|guides|templates/*.md -> docs/<dir>/*.md    (copied verbatim, if present)
  SPEC.md -> docs/SPEC.md                           (copied verbatim, if present)
  plugin.yml suite: -> docs/plugin-docs.json        (live session preview)

Only source dirs that exist are rendered, so a plugin without guides/ or rules/
is fine. docs/ is a pure render target. Any other files under docs/ (hand-written
pages, images) are left untouched.
"""
from __future__ import annotations

import pathlib
import shutil

from . import gen_plugin_docs
from ._common import plugin_root

COPY_DIRS = ("rules", "guides", "templates")


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            seen += 1
            if seen == 2:
                return "".join(lines[i + 1:]).lstrip("\n")
    return text  # no frontmatter fence -> pass through


def run(root: str | pathlib.Path | None = None) -> int:
    r = plugin_root(root)
    docs = r / "docs"

    skills = sorted((r / "skills").glob("*/SKILL.md"))
    if skills:
        (docs / "skills").mkdir(parents=True, exist_ok=True)
        for s in skills:
            (docs / "skills" / f"{s.parent.name}.md").write_text(_strip_frontmatter(s.read_text()))

    for name in COPY_DIRS:
        src = r / name
        mds = sorted(src.glob("*.md")) if src.is_dir() else []
        if mds:
            (docs / name).mkdir(parents=True, exist_ok=True)
            for f in mds:
                shutil.copyfile(f, docs / name / f.name)

    # the plugin's spec, if it keeps one, so the docs site can serve it
    spec = r / "SPEC.md"
    if spec.is_file():
        docs.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec, docs / "SPEC.md")

    return gen_plugin_docs.run(root)
