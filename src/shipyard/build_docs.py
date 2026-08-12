"""Render a plugin's docs/ from its sources, so there's no parallel doc artifact.

  assets/* -> docs/*                                (resource paths, copied first)
  skills/<name>/SKILL.md -> docs/skills/<name>.md   (YAML frontmatter stripped)
  rules|guides|templates/*.md -> docs/<dir>/*.md    (copied verbatim, if present)
  SPEC.md -> docs/spec.md                           (copied verbatim, if present)
  plugin.yml suite: -> docs/plugin-docs.json        (live session preview)
  plugin.yml suite: -> docs/_home.md                (home page, embedded by README)
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

import yaml

from . import gen_plugin_docs
from ._common import load_plugin, plugin_root

COPY_DIRS = ("rules", "guides", "templates")

HUB = "https://chris-peterson.github.io"
MARKETPLACE = "chris-peterson"
MARKETPLACE_REPO = "chris-peterson/claude-marketplace"

# The kinds this build renders pages for; the rest read as plain names.
ARTIFACT_PAGES = {"skills": "skills", "rules": "rules"}

_PLUGIN_ROOT_PATH = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"'\s]+)")

# An extension with no entry falls through to an unhighlighted fence, which
# renders; a plugin's `docs:` block decides which highlighters actually load.
SCRIPT_LANGS = {".sh": "bash", ".bash": "bash", ".py": "python", ".js": "javascript"}

# Values resolve through the host theme's tokens, so the page follows the site
# into light or dark. The block travels inside the generated page: the docs and
# their presentation ship together, with no second deploy to keep in step.
HOME_STYLE = """<style>
.markdown-section .ph-tags{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 20px}
.markdown-section .ph-tag{display:inline-flex;align-items:center;gap:7px;padding:3px 11px;
  border:1px solid var(--border-subtle);border-radius:20px;text-decoration:none;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
  color:var(--muted-color);white-space:nowrap}
.markdown-section a.ph-tag:hover{color:var(--base-color);border-color:var(--muted-color);
  text-decoration:none}
.markdown-section .ph-tag img{display:block;border-radius:3px}
.markdown-section .ph-lede{font-size:1.3em;line-height:1.5;margin:0 0 16px;color:var(--base-color)}
.markdown-section .ph-peer{vertical-align:-4px;margin-right:8px;border-radius:4px}
</style>"""
ARTIFACT_HEADINGS = {
    "skills": ("Skills", "Skill"),
    "rules": ("Rules", "Rule"),
    "hooks": ("Hooks", "Hook"),
    "commands": ("Commands", "Command"),
    "agents": ("Agents", "Agent"),
}

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


def _declared_hooks(r: pathlib.Path) -> list[tuple[str, dict, str]]:
    """(name, declaration, script path) for each hook in hooks.yml, the source of
    record. The script path is "" when the command doesn't run one out of the
    plugin (an inline shell one-liner)."""
    hooks_yml = r / "hooks" / "hooks.yml"
    if not hooks_yml.is_file():
        return []
    out = []
    for entry in (yaml.safe_load(hooks_yml.read_text()) or {}).get("hooks") or []:
        match = _PLUGIN_ROOT_PATH.search(entry.get("command", ""))
        path = match.group(1) if match else ""
        name = pathlib.PurePosixPath(path).stem if path else entry.get("event", "hook")
        out.append((name, entry, path))
    return out


def _render_hooks_md(r: pathlib.Path) -> str:
    """The hooks page: a section per hook carrying what hooks.yml declares and
    the script it runs, so a reader following a hook from the docs stays in the
    docs and reads what runs on the page."""
    out = ["<!-- Generated by shipyard build-docs from hooks/hooks.yml. Do not edit. -->", "",
           "# Hooks", "",
           "What this plugin does without being asked: each hook below is wired to a "
           "Claude Code event, and runs whenever that event fires.", ""]
    for name, entry, path in _declared_hooks(r):
        out += [f"## {name}", ""]
        if entry.get("description"):
            out += [entry["description"], ""]
        matcher = entry.get("matcher")
        out += ["| Event | Matcher | Command |", "|---|---|---|",
                "| `{}` | {} | `{}` |".format(
                    entry.get("event", ""),
                    f"`{matcher}`" if matcher else "—",
                    _cell(entry.get("command", ""))),
                ""]
        script = (r / path) if path else None
        if script and script.is_file():
            lang = SCRIPT_LANGS.get(script.suffix, "")
            out += [f"```{lang}", script.read_text().rstrip("\n"), "```", ""]
    return "\n".join(out)


def _cell(text: str) -> str:
    """Flatten a description into a table cell: a wrapped source line would end
    the row, and a literal pipe would start a new column."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _skill_order(entries: dict, curated: list[str]) -> list[str]:
    """The plugin's own `cmds` order first — that's the author saying which
    skills matter — then whatever else it ships."""
    lead = [name for name in curated if name in entries]
    return lead + [name for name in entries if name not in lead]


def _artifact_table(kind: str, entries: dict, curated: dict, plugin: str,
                    sources: dict) -> list[str]:
    plural, singular = ARTIFACT_HEADINGS[kind]
    page = ARTIFACT_PAGES.get(kind)
    out = [f"## {plural}", ""]
    # gen-describe records the whole event→target wiring under the reserved name
    # `hooks` — that entry is hooks.json, not a hook. It describes the set, so it
    # leads the section rather than posing as a row in it.
    if kind == "hooks" and "hooks" in entries:
        out += [_cell(entries["hooks"]), ""]
        entries = {name: text for name, text in entries.items() if name != "hooks"}
    out += [f"| {singular} | What it does |", "|---|---|"]
    for name in (_skill_order(entries, list(curated)) if kind == "skills" else entries):
        label = f"/{plugin}:{name}" if kind == "skills" else name
        if page:
            cell = f"[`{label}`](/{page}/{name})"
        elif sources.get(name):
            cell = f"[`{label}`]({sources[name]})"
        else:
            cell = f"`{label}`"
        out.append(f"| {cell} | {_cell(curated.get(name) or entries[name])} |")
    return out + [""]


def _render_home_md(spec: dict, r: pathlib.Path) -> str:
    """The plugin's home page, projected from the same suite: block the bridge.ai
    catalog card is built from — the card's content, written as documentation.

    It is markdown rather than a rendered widget so the docs site styles it as
    its own: the theme's tables and headings, the copy button docsify already
    puts on a code fence, real links a reader can middle-click. A page embeds it
    with `[](_home.md ':include')`, so a plugin opts in with one line and keeps
    whatever it wants to say above and below."""
    name = spec.get("name", "")
    suite = spec.get("suite") or {}
    describe = suite.get("describe") or {}

    # `cmds` is the author's own copy for the skills a user reaches for, so it
    # wins over the description generated from the skill's own frontmatter.
    curated = {}
    for entry in (suite.get("cmds") or []):
        label, desc = entry[0], entry[1]
        curated[label.rsplit(":", 1)[-1] if ":" in label else label.lstrip("/")] = desc

    out = ["<!-- Generated by shipyard build-docs from plugin.yml. Do not edit. -->", "",
           HOME_STYLE, ""]

    if spec.get("version"):
        # `releases/latest` rather than a tag built from the version: it resolves
        # without knowing whether the repo tags `v1.5.0` or `1.5.0`.
        repository = (spec.get("repository") or "").rstrip("/")
        version = f'v{spec["version"]}'
        tag = (f'<a class="ph-tag" href="{repository}/releases/latest">{version}</a>'
               if "github.com" in repository else f'<span class="ph-tag">{version}</span>')
        out += [f'<p class="ph-tags">{tag}</p>', ""]

    if suite.get("gloss"):
        # Not a blockquote: the theme renders one as a tip callout, which files
        # the plugin's one-line summary as an aside.
        out += [f'<p class="ph-lede">{html.escape(suite["gloss"])}</p>', ""]
    for key in ("pitch", "what"):
        if suite.get(key):
            out += [suite[key], ""]

    out += ["## Install", "", "```bash",
            f"claude plugin marketplace add {MARKETPLACE_REPO}",
            f"claude plugin install {name}@{MARKETPLACE}",
            "```", ""]

    pages = {name: f"/hooks?id={name}" for name, _, _ in _declared_hooks(r)}
    for kind in ARTIFACT_HEADINGS:
        if describe.get(kind):
            out += _artifact_table(kind, describe[kind], curated, name, pages)

    deps = suite.get("dependencies") or []
    if deps:
        # Resolving to the hub is what identifies a peer — one a reader can act
        # on without leaving the docs — so peers lead and carry their own mark.
        resolved = [(dep, dep.get("url") or f"{HUB}/{dep['name']}") for dep in deps]
        peers = [(d, u) for d, u in resolved if u.startswith(HUB + "/")]
        out += ["## Works with", "", "| Project | What it adds |", "|---|---|"]
        for dep, url in peers + [pair for pair in resolved if pair not in peers]:
            peer = (dep, url) in peers
            mark = (f'<img class="ph-peer" src="{HUB}/{dep["name"]}/favicon.svg" '
                    f'alt="" width="18" height="18">') if peer else ""
            link = f"{mark}[{dep['name']}]({url})" + ("" if peer else " ↗")
            adds = _cell(dep.get("reason", ""))
            out.append(f"| {link} | {'**Required.** ' if dep.get('required') else ''}{adds} |")
        out.append("")

    return "\n".join(out)


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

    # The home page, for a README that embeds it. Always rendered when the
    # source is there — like every other page under docs/, it costs nothing
    # until something links to it.
    if plugin.get("suite"):
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "_home.md").write_text(_render_home_md(plugin, r))

    # The page the home page's hook rows point at.
    if _declared_hooks(r):
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "hooks.md").write_text(_render_hooks_md(r))

    rc = gen_plugin_docs.run(root)
    _check_refs(docs)
    return rc
