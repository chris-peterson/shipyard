"""Render a plugin's docs/ from its sources, so there's no parallel doc artifact.

  skills/<name>/SKILL.md -> docs/skills/<name>.md   (YAML frontmatter stripped)
  rules|guides|templates/*.md -> docs/<dir>/*.md    (copied verbatim, if present)
  SPEC.md -> docs/spec.md                           (copied verbatim, if present)
  plugin.yml suite: -> docs/plugin-docs.json        (live session preview)
  plugin.yml docs: -> docs/index.html               (docsify bootstrap, if present)

Only source dirs that exist are rendered, so a plugin without guides/ or rules/
is fine. docs/ is a pure render target. Any other files under docs/ (hand-written
pages, images) are left untouched.
"""
from __future__ import annotations

import html
import pathlib
import shutil

from . import gen_plugin_docs
from ._common import load_plugin, plugin_root

COPY_DIRS = ("rules", "guides", "templates")


def _render_index_html(spec: dict) -> str:
    """The docsify bootstrap, projected from plugin.yml. Held here so a fix (or a
    bump of the shared bundle) lands in one place instead of drifting across every
    plugin's hand-copied index.html. Per-plugin variance is `name`/`description`
    (packaging fields) and the `docs:` block (code_languages, mermaid); the
    session player is emitted only when the plugin ships a suite: preview."""
    name = html.escape(spec.get("name", ""))
    description = html.escape(spec.get("description", ""))
    docs = spec.get("docs") or {}
    langs = ", ".join(f"'{lang}'" for lang in (docs.get("code_languages") or ["bash", "yaml", "json"]))

    init = [f"      name: '{spec.get('name', '')}',", f"      code_languages: [{langs}]"]
    if docs.get("mermaid"):
        init[-1] += ","
        init.append("      plugins: ['mermaid']")

    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="UTF-8">',
        f"  <title>{name}</title>",
        '  <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1" />',
        f'  <meta name="description" content="{description}">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0, minimum-scale=1.0">',
        '  <link rel="icon" type="image/svg+xml" href="favicon.svg">',
        "</head>",
        "<body>",
        '  <div id="app">Loading…</div>',
        '  <script src="https://chris-peterson.github.io/js/docsify-shared.js"></script>',
        "  <script>",
        "    // subMaxLevel: 0 stops docsify auto-injecting the current page's own",
        "    // headings into the sidebar as a phantom child tree (Home sprouting its",
        "    // ## headings, a skill page its steps). Set before initProject: it only",
        "    // fills a default for keys not already present on window.$docsify.",
        "    window.$docsify = { subMaxLevel: 0 };",
        "    initProject({",
        *init,
        "    });",
        "  </script>",
    ]
    if spec.get("suite"):
        lines += [
            '  <link rel="stylesheet" href="https://chris-peterson.github.io/claude-marketplace/session.css">',
            '  <script src="https://chris-peterson.github.io/claude-marketplace/session-player.js"></script>',
        ]
    lines += ["</body>", "</html>", ""]
    return "\n".join(lines)


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

    # the plugin's spec, if it keeps one, so the docs site can serve it.
    # Output is lowercase docs/spec.md so the docsify route is /spec (the source
    # stays SPEC.md — the canonical name the ambient rules reference).
    spec = r / "SPEC.md"
    if spec.is_file():
        docs.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec, docs / "spec.md")

    # docsify bootstrap, projected from plugin.yml. Opt-in: a plugin that hasn't
    # declared a docs: block keeps its hand-written index.html untouched.
    plugin = load_plugin(root)
    if plugin.get("docs") is not None:
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "index.html").write_text(_render_index_html(plugin))

    return gen_plugin_docs.run(root)
