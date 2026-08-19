"""Render a plugin's docs/ from its sources, so there's no parallel doc artifact.

  assets/* -> docs/*                                (resource paths, copied first)
  skills/<name>/SKILL.md -> docs/skills/<name>.md   (YAML frontmatter stripped)
  skills/<name>/references/*.md -> docs/skills/<name>/references/*.md
  rules|guides|templates|references/*.md -> docs/<dir>/*.md   (if present)
  SPEC.md -> docs/spec.md                           (copied verbatim, if present)
  STATUS.md -> docs/status.md                       (copied verbatim, if present)
  spec/<version>/SPEC.md -> docs/spec/<version>.md  (a versioned spec, if kept)
  the committed CLI manifest -> docs/cli.md         (command reference, if present)
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

A rendered page's *links* need one step more than copying, because rendering
moves the page: a skill's `../../references/x.md` was written against
`skills/<name>/SKILL.md` and is served from `skills/<name>.md`. Each source's
published route is recorded as it renders, and the links are then rewritten to
those routes — so one link works in the checkout, on the forge, and on the site.
`links.py` holds the docsify model both that and the check read from.
"""
from __future__ import annotations

import html
import pathlib
import re
import shutil
import urllib.parse

import yaml

from . import gen_cli_manifest, gen_plugin_docs, links
from ._common import block, load_plugin, plugin_root
from .gen_hooks_json import load_hooks

COPY_DIRS = ("rules", "guides", "templates", "references")

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
.markdown-section .ph-cli{color:var(--theme-color);text-transform:uppercase;letter-spacing:.14em;
  font-size:10.5px;border-color:color-mix(in srgb,var(--theme-color) 32%,transparent)}
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

# Publish assets/ when plugin.yml names nothing.
DEFAULT_RESOURCES = ("assets",)

# A file reference: an `<img src>` or a markdown image names a file that has to
# exist in the artifact. A `[text](page.md)` link names a docsify route instead,
# and is checked separately against the model in `links.py`.
_REF_PATTERNS = (
    re.compile(r'\ssrc\s*=\s*["\']([^"\']+)["\']'),
    re.compile(r'!\[[^\]]*\]\(\s*([^)\s]+)'),
)


def _render_index_html(spec: dict) -> str:
    """The docsify bootstrap, projected from plugin.yml. Held here so a fix (or a
    bump of the shared bundle) lands in one place instead of drifting across every
    plugin's hand-copied index.html. Per-plugin variance is `name`/`description`
    (packaging fields) and the `docs:` block (code_languages, mermaid); the
    session player is emitted only when the plugin ships a suite: preview."""
    name = html.escape(spec.get("name", ""))
    description = html.escape(spec.get("description", ""))
    docs = block(spec, "docs", "plugin.yml")
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
    for entry in load_hooks(hooks_yml):
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
                    sources: dict, published: set[str]) -> list[str]:
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
        # A row links only where there's a page to land on. `suite.describe` is a
        # committed projection, so between releases it can still name an artifact
        # whose source is gone — and a row linking that is a 404 in the one table
        # every reader starts from.
        route = f"/{page}/{name}" if page else sources.get(name)
        landed = route and route.split("?")[0] in published
        cell = f"[`{label}`]({route})" if landed else f"`{label}`"
        out.append(f"| {cell} | {_cell(curated.get(name) or entries[name])} |")
    return out + [""]


def _render_home_md(spec: dict, r: pathlib.Path, published: set[str]) -> str:
    """The plugin's home page, projected from the same suite: block the bridge.ai
    catalog card is built from — the card's content, written as documentation.

    It is markdown rather than a rendered widget so the docs site styles it as
    its own: the theme's tables and headings, the copy button docsify already
    puts on a code fence, real links a reader can middle-click. A page embeds it
    with `[](_home.md ':include')`, so a plugin opts in with one line and keeps
    whatever it wants to say above and below."""
    name = spec.get("name", "")
    suite = block(spec, "suite", "plugin.yml")
    describe = suite.get("describe") or {}

    # `cmds` is the author's own copy for the skills a user reaches for, so it
    # wins over the description generated from the skill's own frontmatter.
    curated = {}
    for entry in (suite.get("cmds") or []):
        label, desc = entry[0], entry[1]
        curated[label.rsplit(":", 1)[-1] if ":" in label else label.lstrip("/")] = desc

    out = ["<!-- Generated by shipyard build-docs from plugin.yml. Do not edit. -->", "",
           HOME_STYLE, ""]

    tags = []
    if suite.get("cli"):
        # The same mark the catalog card carries, for the same reason: a plugin
        # that ships a command you run in your own shell reads differently from
        # one a session only reaches for, and that is worth stating up front.
        tags.append('<span class="ph-tag ph-cli">cli</span>')
    if spec.get("version"):
        # `releases/latest` rather than a tag built from the version: it resolves
        # without knowing whether the repo tags `v1.5.0` or `1.5.0`.
        repository = (spec.get("repository") or "").rstrip("/")
        version = f'v{spec["version"]}'
        tags.append(f'<a class="ph-tag" href="{repository}/releases/latest">{version}</a>'
                    if "github.com" in repository
                    else f'<span class="ph-tag">{version}</span>')
    if tags:
        out += [f'<p class="ph-tags">{"".join(tags)}</p>', ""]

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
            out += _artifact_table(kind, describe[kind], curated, name, pages, published)

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


def declared_resources(spec: dict) -> list[str] | None:
    """The resource paths from plugin.yml's `docs:` block, or None when it names
    none — which means DEFAULT_RESOURCES applies, not "publish nothing".

    This is a fact about the plugin, so it lives with every other one, in the
    plugin's own descriptor. Reading it from the checkout is also what lets a
    local `build-docs` reproduce CI's exactly: the paths used to arrive as a
    workflow input, so they were the one thing a run outside CI couldn't see."""
    declared = spec.get("resources")
    if declared is None:
        return None
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list) or not all(isinstance(p, str) for p in declared):
        raise SystemExit(
            "shipyard: plugin.yml `docs: resources:` must be a path or a list of "
            f"paths, got {declared!r}")
    return [p.strip() for p in declared if p.strip()] or None


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


def _local_refs(text: str) -> list[str]:
    """The file references in a page that have to resolve inside the artifact.
    A scheme (https:, data:, mailto:), a root-relative path, or a bare fragment
    resolves somewhere this build can't see, so none of those are ours to check."""
    refs = []
    prose = "\n".join(links.mask_code_spans(line) for _, line in links.prose_lines(text))
    for pattern in _REF_PATTERNS:
        for ref in pattern.findall(prose):
            ref = ref.split("#")[0].split("?")[0].strip().strip("<>")
            # The reference is a URL; the thing on disk is a path. `my%20hero.png`
            # and `my hero.png` are the same file, and only the decoded form exists.
            ref = urllib.parse.unquote(ref)
            if ref and not ref.startswith("/") and not links.SCHEME.match(ref):
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
            if not links.exists_exact(docs, ref):
                broken.append(f"  {page.relative_to(docs.parent).as_posix()} -> {ref}")
    if broken:
        raise SystemExit(
            "shipyard: docs reference files the published tree doesn't carry:\n"
            + "\n".join(broken)
            + "\n\nCommit them under docs/, or name their directory in "
              "plugin.yml's `docs: resources:`.")


def _rewrite_links(docs: pathlib.Path,
                   rendered: list[tuple[str, pathlib.Path]]) -> None:
    """Point each rendered page's links at the routes the site serves, now that
    every source's destination is known. Only pages that came from a source are
    touched: a hand-written page under docs/ was written against the site and
    already says `/skills/thing`."""
    routes = {source: links.route_of(docs, page) for source, page in rendered}
    for source, page in rendered:
        text = page.read_text()
        rewritten = links.rewrite(text, source, routes)
        if rewritten != text:
            page.write_text(rewritten)


def _check_links(docs: pathlib.Path) -> None:
    """Fail on a link that 404s on the live site, or lands on a page with no such
    anchor. A dead link fails silently by construction — docsify renders its own
    404 page inside a page that loaded fine, and the deploy is green — so this
    check is the only thing that reports one before a reader does."""
    broken, dead_anchors = [], []
    for page in sorted(docs.rglob("*.md")):
        where = page.relative_to(docs.parent).as_posix()
        text = page.read_text(errors="replace")
        for href in links.local_links(text):
            target = links.page_for(docs, href)
            if target is None:
                broken.append(f"  {where} -> {href}")
                continue
            _, fragment = links.split_fragment(href)
            if fragment and fragment not in links.anchors(target.read_text(errors="replace")):
                dead_anchors.append(f"  {where} -> {href}")
    if not broken and not dead_anchors:
        return
    report = ["shipyard: docs links that 404 on the published site:"]
    if broken:
        report += ["", "No page at that route:", *broken]
    if dead_anchors:
        report += ["", "Page resolves, but carries no such anchor:", *dead_anchors]
    report += ["", "A link written for the checkout is rewritten to its published "
               "route automatically — one that isn't names a page this build "
               "doesn't publish. Publish it, or point the link at a page that is."]
    raise SystemExit("\n".join(report))


def run(root: str | pathlib.Path | None = None) -> int:
    r = plugin_root(root)
    docs = r / "docs"
    plugin = load_plugin(root)

    # First, so that everything projected below wins a name collision — shipyard
    # owns index.html and the rendered pages, and a resource quietly replacing one
    # of them would be a build whose output depends on copy order.
    _publish_resources(r, docs, declared_resources(block(plugin, "docs", "plugin.yml")))

    # Each rendered page paired with the source it came from, so the link rewrite
    # below can resolve that page's links the way a reader of the source does.
    rendered: list[tuple[str, pathlib.Path]] = []

    def render(source: pathlib.Path, dest: pathlib.Path, text: str | None = None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # A leftover page differing only in case (an earlier build's docs/SPEC.md)
        # is the file a write to docs/spec.md lands in on macOS, so the tree ends
        # up named one way locally and another in CI — and the routes follow. The
        # published name is this build's to decide, so the variant goes.
        for entry in dest.parent.iterdir():
            if entry.name != dest.name and entry.name.lower() == dest.name.lower():
                entry.unlink()
        dest.write_text(source.read_text() if text is None else text)
        rendered.append((source.relative_to(r).as_posix(), dest))

    for s in sorted((r / "skills").glob("*/SKILL.md")):
        render(s, docs / "skills" / f"{s.parent.name}.md", _strip_frontmatter(s.read_text()))
        # A skill's own references travel with it. They sit a level deeper than the
        # root-level dirs below, and keeping that shape is what lets the skill's
        # `references/x.md` link resolve on the site as well as in the checkout.
        for f in sorted((s.parent / "references").glob("*.md")):
            render(f, docs / "skills" / s.parent.name / "references" / f.name)

    for name in COPY_DIRS:
        src = r / name
        for f in sorted(src.glob("*.md")) if src.is_dir() else []:
            render(f, docs / name / f.name)

    # the plugin's spec and ledger, if it keeps them, so the docs site can serve
    # them. Output is lowercased so the routes are /spec and /status (the sources
    # stay SPEC.md and STATUS.md — the canonical names the ambient rules use).
    for name, page in (("SPEC.md", "spec.md"), ("STATUS.md", "status.md")):
        source = r / name
        if source.is_file():
            render(source, docs / page)

    # A versioned spec (`spec/v1/SPEC.md`, `spec/vnext/SPEC.md`) is served at
    # /spec/<version>. Publishing it is what lets a ledger cite the contract it
    # actually tracks: tack's STATUS.md links spec/v1/SPEC.md, which is right in
    # the checkout and reaches nothing on a site that only carries the root spec.
    for source in sorted(r.glob("spec/*/SPEC.md")):
        render(source, docs / "spec" / f"{source.parent.name}.md")

    # the CLI's command reference, so the docs site stops depending on a
    # hand-maintained command table that drifts from the binary.
    if page := gen_cli_manifest.docs_page(root):
        docs.mkdir(parents=True, exist_ok=True)
        (docs / gen_cli_manifest.DOCS_PAGE).write_text(page)

    # docsify bootstrap, projected from plugin.yml. Opt-in: a plugin that hasn't
    # declared a docs: block keeps its hand-written index.html untouched.
    if plugin.get("docs") is not None:
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "index.html").write_text(_render_index_html(plugin))

    # The page the home page's hook rows point at. Rendered before the home page,
    # which links only the routes that exist by the time it's written.
    if _declared_hooks(r):
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "hooks.md").write_text(_render_hooks_md(r))

    # The home page, for a README that embeds it. Always rendered when the
    # source is there — like every other page under docs/, it costs nothing
    # until something links to it.
    if plugin.get("suite"):
        docs.mkdir(parents=True, exist_ok=True)
        published = {links.route_of(docs, p) for p in docs.rglob("*.md")}
        (docs / "_home.md").write_text(_render_home_md(plugin, r, published))

    _rewrite_links(docs, rendered)

    rc = gen_plugin_docs.run(root)
    _check_refs(docs)
    _check_links(docs)
    return rc
