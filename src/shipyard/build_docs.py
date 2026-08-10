"""Render a plugin's docs/ from its sources, so there's no parallel doc artifact.

  assets/* -> docs/*                                (resource paths, copied first)
  skills/<name>/SKILL.md -> docs/skills/<name>.md   (YAML frontmatter stripped)
  rules|guides|templates/*.md -> docs/<dir>/*.md    (copied verbatim, if present)
  SPEC.md -> docs/spec.md                           (copied verbatim, if present)
  plugin.yml suite: -> docs/plugin-docs.json        (live session preview)
  plugin.yml docs: -> docs/index.html               (docsify bootstrap, if present)

Only source dirs that exist are rendered, so a plugin without guides/ or rules/
is fine. docs/ is a pure render target. Any other files under docs/ (hand-written
pages, images) are left untouched.

Only docs/ is published, so a page referencing a file outside it 404s on the
live site with nothing failing to announce it. Resource paths close that: each
declared path is copied into the published tree, and every local reference the
rendered pages make is then resolved against that tree, so an unresolvable one
fails the build instead of shipping a blank image.
"""
from __future__ import annotations

import html
import os
import pathlib
import re
import shutil
import urllib.parse

from . import gen_plugin_docs
from ._common import load_plugin, plugin_root

COPY_DIRS = ("rules", "guides", "templates")

# Publish assets/ when the caller names nothing. Declared here rather than as the
# action/workflow input default so raising it doesn't need every caller to re-pin.
DEFAULT_RESOURCES = ("assets",)

# Only file references are checked: an <img src> or a markdown image is a file
# that has to exist in the artifact, whereas a [text](page.md) link is a docsify
# route, which resolves by a rule this build doesn't own.
_REF_PATTERNS = (
    re.compile(r'\ssrc\s*=\s*["\']([^"\']+)["\']'),
    re.compile(r'!\[[^\]]*\]\(\s*([^)\s]+)'),
)
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_INLINE_CODE = re.compile(r"`[^`]*`")
_FENCES = ("```", "~~~")


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


def resources_from_env() -> list[str] | None:
    """The resource paths the CI entry point declares, newline- or comma-separated.
    Carried by environment rather than a flag because the value originates in a
    workflow input, and interpolating one into a `run:` script is a script
    injection. Unset or empty means the caller named nothing, not "publish
    nothing" — DEFAULT_RESOURCES then applies."""
    paths = [p.strip() for p in re.split(r"[\n,]", os.environ.get("SHIPYARD_RESOURCES", ""))]
    return [p for p in paths if p] or None


def _publish_resources(r: pathlib.Path, docs: pathlib.Path,
                       resources: list[str] | None) -> None:
    """Copy the plugin's resource paths into the published tree, flattening a
    directory's contents to the docs root the way each plugin's own `cp assets/*
    docs/` step did before shipyard replaced it — so `<img src="hero.svg">`
    keeps resolving.

    A path the caller declared must exist: naming it and having it silently do
    nothing is the failure this whole mechanism exists to end. The default is
    the exception, since it applies to plugins that ship no assets/ at all."""
    declared = resources is not None
    for name in (resources if declared else DEFAULT_RESOURCES):
        src = (r / name).resolve()
        # An ancestor of docs/, not just docs/ itself: copying `.` would fold the
        # whole repo — docs/ included — back into docs/.
        if not src.is_relative_to(r) or docs.resolve().is_relative_to(src):
            raise SystemExit(f"shipyard: resource path must be inside the plugin, and below docs/: {name}")
        if not src.exists():
            if declared:
                raise SystemExit(f"shipyard: declared resource path not found: {name}")
            continue
        docs.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, docs, dirs_exist_ok=True)
        else:
            shutil.copyfile(src, docs / src.name)


def _strip_code(text: str) -> str:
    """Drop fenced blocks and inline spans, whose contents render as literal text.
    A guide showing the reader `![Before](before-login.png)` as an example is not
    referencing a file, and checking it would fail a build over prose."""
    kept, fence = [], None
    for line in text.splitlines():
        if fence is None:
            marker = next((f for f in _FENCES if line.lstrip().startswith(f)), None)
            if marker:
                fence = marker
                continue
            kept.append(_INLINE_CODE.sub(" ", line))
        elif line.lstrip().startswith(fence):
            fence = None
    return "\n".join(kept)


def _local_refs(text: str) -> list[str]:
    """The file references in a page that have to resolve inside the artifact.
    A scheme (https:, data:, mailto:), a root-relative path, or a bare fragment
    resolves somewhere this build can't see, so none of those are ours to check."""
    refs = []
    for pattern in _REF_PATTERNS:
        for ref in pattern.findall(_strip_code(text)):
            ref = ref.split("#")[0].split("?")[0].strip().strip("<>")
            # The reference is a URL; the thing on disk is a path. `my%20hero.png`
            # and `my hero.png` are the same file, and only the decoded form exists.
            ref = urllib.parse.unquote(ref)
            if ref and not ref.startswith("/") and not _SCHEME.match(ref):
                refs.append(ref)
    return refs


def _check_refs(docs: pathlib.Path) -> None:
    """Fail on a rendered page pointing at a file the published tree doesn't
    carry. Runs last, over the tree as it will be uploaded, because a reference
    is only broken relative to what actually ships.

    Every reference resolves against the docs root, not the page's own directory,
    however deep the page sits. Both halves of the site agree on that: the shared
    docsify bootstrap sets `relativePath: false`, and a raw <img src> is resolved
    by the browser against index.html's URL, since the route lives in the hash."""
    broken = []
    for page in sorted(docs.rglob("*.md")) + sorted(docs.rglob("*.html")):
        for ref in _local_refs(page.read_text(errors="replace")):
            if not (docs / ref).exists():
                broken.append(f"  {page.relative_to(docs.parent).as_posix()} -> {ref}")
    if broken:
        raise SystemExit(
            "shipyard: docs reference files the published tree doesn't carry:\n"
            + "\n".join(broken)
            + "\n\nCommit them under docs/, or name their directory in the "
              "build's `resources` input.")


def run(root: str | pathlib.Path | None = None,
        resources: list[str] | None = None) -> int:
    r = plugin_root(root)
    docs = r / "docs"

    # First, so that everything projected below wins a name collision — shipyard
    # owns index.html and the rendered pages, and a resource quietly replacing one
    # of them would be a build whose output depends on copy order.
    _publish_resources(r, docs, resources)

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

    rc = gen_plugin_docs.run(root)
    _check_refs(docs)
    return rc
