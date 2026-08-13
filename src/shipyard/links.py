"""How docsify resolves a link, modelled offline.

Two consumers, one model. ``build_docs`` rewrites a source page's repo-relative
links into site routes as it renders, then checks that every route on every
published page resolves. Both need the same three answers: which text in a page
is a link at all, which file docsify fetches for a route, and which anchors a
page offers.

The reason a rewrite is needed rather than a docsify setting: rendering *moves* a
page to a different depth. ``skills/<name>/SKILL.md`` is published as
``skills/<name>.md``, so a link the source wrote as ``../../references/x.md`` —
correct in the checkout, and correct on the forge — climbs one level too far from
where the page now sits. No ``relativePath`` value fixes that, because the link
was written against a depth the published tree doesn't have.

The slug rules are docsify's own (``src/core/router/util`` and the heading
renderer), and they are unguessable in two places worth naming: the punctuation
set it strips **keeps** the hyphen and the underscore, and a heading's inline
markup is dropped before slugging — so ``#### `LOCATE-01` `` and ``#### LOCATE-01``
both anchor at ``locate-01``.
"""
from __future__ import annotations

import pathlib
import re
import urllib.parse

# A run of N backticks closed by the same run. The double-backtick form matters:
# a guide showing the reader ``[`spec.md`](spec.md)`` is quoting a link, not
# making one, and a single-backtick pattern tears that span in half and then
# reads the wreckage as a reference.
CODE_SPAN = re.compile(r"(`+).+?\1")
FENCES = ("```", "~~~")

# An inline link, minus images: `![alt](shot.png)` names a file that has to exist
# in the artifact, while `[text](page.md)` names a route. They fail differently,
# so they're found separately.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*([^)\s]+)")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

# What docsify strips from a heading before slugging it. Everything absent from
# this set survives — the hyphen and the underscore included, which is why
# `LOCATE-01` keeps its hyphen.
_SLUG_STRIP = re.compile(
    "[\u2000-\u206f\u2e00-\u2e7f"
    + re.escape("\\'!\"#$%&()*+,./:;<=>?@[]^`{|}~")
    + "]"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>\d]+>")
_EXPLICIT_ID = re.compile(r"id=[\"']([^\"']+)[\"']")
_DOCSIFY_MARKER = re.compile(r"\{docsify-ignore(-all)?\}")


def mask_code_spans(line: str) -> str:
    """The line with every inline code span blanked to spaces. Same length as the
    input, so a match offset still points at the original text — the rewrite
    edits in place and can't afford a shifted index."""
    return CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)


def prose_lines(text: str):
    """(index, line) for each line that renders as prose. Fenced blocks are
    skipped whole: a guide documenting markdown is showing the reader a link, not
    making one."""
    fence = None
    for i, line in enumerate(text.splitlines()):
        if fence is None:
            marker = next((f for f in FENCES if line.lstrip().startswith(f)), None)
            if marker:
                fence = marker
                continue
            yield i, line
        elif line.lstrip().startswith(fence):
            fence = None


def local_links(text: str) -> list[str]:
    """Every link in a page that has to resolve inside the published tree. A
    scheme, a protocol-relative host, or a bare fragment resolves somewhere this
    build can't see."""
    out = []
    for _, line in prose_lines(text):
        for href in LINK.findall(mask_code_spans(line)):
            href = href.strip().strip("<>")
            if href and not href.startswith(("#", "//")) and not SCHEME.match(href):
                out.append(href)
    return out


def slugify(heading_text: str) -> str:
    """The anchor docsify gives a heading. Inline markup goes first, so the slug
    is derived from what the reader sees."""
    text = _DOCSIFY_MARKER.sub("", heading_text)
    text = _MD_LINK_TEXT.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    text = _SLUG_STRIP.sub("", text.strip().lower())
    text = re.sub(r"\s", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return re.sub(r"^(\d)", r"_\1", text)


def anchors(text: str) -> set[str]:
    """Every fragment the page answers to: its headings' slugs, plus any explicit
    `id=` target. Repeated headings take docsify's `-1`, `-2` suffixes."""
    seen: dict[str, int] = {}
    out = set(_EXPLICIT_ID.findall(text))
    for _, line in prose_lines(text):
        match = _HEADING.match(line)
        if not match:
            continue
        slug = slugify(match.group(2))
        if not slug:
            continue
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        out.add(slug if not count else f"{slug}-{count}")
    return out


def split_fragment(href: str) -> tuple[str, str]:
    """(path, fragment) for a link. docsify deep-links with `?id=`; a plain `#`
    fragment means the same thing to a reader, and both have to resolve."""
    path, hash_mark, rest = href.partition("#")
    if hash_mark:
        return path, urllib.parse.unquote(rest)
    path, _, query = href.partition("?")
    if query.startswith("id="):
        return path, urllib.parse.unquote(query[3:].split("&")[0])
    return path, ""


def page_for(docs: pathlib.Path, href: str) -> pathlib.Path | None:
    """The file docsify fetches for a route, or None when nothing does.

    Every route resolves against the docs root, however deep the page linking it
    sits: the shared bootstrap sets `relativePath: false`, and the route lives in
    the URL hash, so there is no page-relative form to honor."""
    path, _ = split_fragment(href)
    path = urllib.parse.unquote(path.strip()).lstrip("/")
    if not path or path.endswith("/"):
        path += "README.md"
    candidates = [path] if path.endswith(".md") else [f"{path}.md", f"{path}/README.md"]
    for candidate in candidates:
        target = docs / candidate
        # A route that climbs out of the tree (`../../references/x`) is what
        # docsify answers with its 404 page. Reporting it is the point, so it
        # must not reach a filesystem probe above docs/ either.
        if not _within(docs, target):
            return None
        if exists_exact(docs, candidate):
            return target
    return None


def _within(root: pathlib.Path, target: pathlib.Path) -> bool:
    try:
        return target.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def exists_exact(root: pathlib.Path, relative: str) -> bool:
    """Whether `relative` names a real file under `root`, matching case at every
    segment.

    `Path.is_file()` answers the host filesystem's question, and macOS answers it
    case-insensitively: `docs/SPEC.md` resolves to `docs/spec.md` there and 404s
    on GitHub Pages, which is case-sensitive. A checker that ran green on the
    author's laptop and let that through would miss the one class of dead link
    nobody can reproduce locally — so the listing decides, not the filesystem."""
    current = root
    parts = pathlib.PurePosixPath(relative).parts
    for i, segment in enumerate(parts):
        try:
            if segment not in {entry.name for entry in current.iterdir()}:
                return False
        except (NotADirectoryError, FileNotFoundError, PermissionError):
            return False
        current = current / segment
    return bool(parts) and current.is_file()


def route_of(docs: pathlib.Path, page: pathlib.Path) -> str:
    """The site route a published page is served at."""
    rel = page.relative_to(docs).as_posix()
    if rel.endswith(".md"):
        rel = rel[: -len(".md")]
    return "/" if rel == "README" else f"/{rel}"


def resolve_source(source: str, path: str) -> str:
    """A link's target as a path in the checkout, relative to the linking file.
    Empty when the link is absolute or climbs past the repo root."""
    if not path or path.startswith("/"):
        return ""
    parts = list(pathlib.PurePosixPath(source).parent.parts)
    for segment in pathlib.PurePosixPath(urllib.parse.unquote(path)).parts:
        if segment == "..":
            if not parts:
                return ""
            parts.pop()
        elif segment != ".":
            parts.append(segment)
    return "/".join(parts)


def rewrite(text: str, source: str, routes: dict[str, str]) -> str:
    """Swap each repo-relative link in a rendered page for the route its target
    is published at. `source` is the page's own path in the checkout, so a link
    resolves the way it does for a reader of the source.

    A link to something the build doesn't publish is left exactly as written. The
    check reports it; rewriting it to a guess would bury a real dead end under a
    plausible-looking route."""
    lines = text.splitlines(keepends=True)
    for i, line in prose_lines(text):
        replacements = []
        for match in LINK.finditer(mask_code_spans(line)):
            path, fragment = split_fragment(match.group(1))
            route = routes.get(resolve_source(source, path))
            if route is not None:
                replacements.append((match.start(1), match.end(1),
                                     f"{route}?id={fragment}" if fragment else route))
        if not replacements:
            continue
        newline = lines[i][len(line):]
        out, last = [], 0
        for start, end, route in replacements:
            out += [line[last:start], route]
            last = end
        lines[i] = "".join(out) + line[last:] + newline
    return "".join(lines)
