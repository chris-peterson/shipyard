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


# A section ends at the next *version* heading, not at the next `## ` of any kind.
# The drafted skeleton buckets a section with `###`, but sections written before
# that used `## Fixed` — and reading those as a version boundary makes the section
# above them look empty, so a release's notes silently become nothing.
_VERSION_HEADING = re.compile(r"^##\s+(?:\[?unreleased\]?|\d.*)$", re.IGNORECASE)


def _section_end(lines: list[str], start: int) -> int:
    for i in range(start + 1, len(lines)):
        if _VERSION_HEADING.match(lines[i]):
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
    if DRAFT_MARKER in body or UNSORTED in body:
        raise SystemExit(
            f"shipyard: {path}'s `## Unreleased` section is still the drafted "
            "worksheet. Sort its lines into the sections that apply, rewrite them "
            "for someone using this, and delete the comment and the Unsorted "
            "heading — then release.")
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


def released_body(version: str, root: str | pathlib.Path | None = None) -> str | None:
    """A released version's section, or None when the file has no such heading.

    `section` is the same read with a publish's demands attached; this one reports
    the file's state without judging it, for a reader that has to describe a
    version the changelog never got a section for.
    """
    path = _changelog(root)
    lines = path.read_text().splitlines()
    header = f"## {version}"
    idx = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if idx is None:
        return None
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


# The draft's own marker. `staged` refuses a section still carrying it, so a
# worksheet can never be published as notes — the whole point of drafting into
# the file rather than into a form is that the file is what gets reviewed.
DRAFT_MARKER = "<!-- shipyard drafted this"
UNSORTED = "### Unsorted"

_SUBSECTION = re.compile(r"^###\s+(.+?)\s*$")


def subsections(body: str) -> dict[str, str]:
    """A section's `### Heading` blocks that have content, by heading.

    Empty ones are dropped rather than reported. The drafted skeleton offers
    Added/Changed/Fixed whether or not a release has any of each, so a heading
    left blank has to read as absent — otherwise every release would infer the
    same bump from the skeleton instead of from what was written under it."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        m = _SUBSECTION.match(line)
        if m:
            current = m.group(1)
            found.setdefault(current, [])
        elif current is not None:
            found[current].append(line)
    return {k: "\n".join(v).strip() for k, v in found.items()
            if "\n".join(v).strip()}


# ---- the teaser --------------------------------------------------------------
# A section is written to be read on the release page: an alert a reader has to
# act on before upgrading, `###` buckets, and a bullet per change whose bold
# lead-in is its headline. A catalog listing a release beside forty others has
# room for the headlines and nothing else, so `teaser` keeps those and drops the
# prose under them. It reads the same shape `retitle` publishes, which is why it
# lives here rather than in the consumer: a bucket heading or a lead-in
# convention that changes changes in one place.
TEASER_ITEMS = 3      # bullets kept per bucket; the rest are counted
TEASER_BUCKETS = 5    # buckets kept per release; the rest are counted
TEASER_CHARS = 96     # a headline is one scannable line, not a paragraph

_ALERT = re.compile(r"^\[!\w+\]$")
_BULLET = re.compile(r"^[-*+]\s+(.+)$")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$")
_LEAD_IN = re.compile(r"\s*\*\*(.+?)\*\*")


def _plain(text: str) -> str:
    """Markdown inline spans flattened to the text they mark up.

    An underscore is only emphasis at a word boundary. `created_at` carries its
    own, and stripping that leaves a word naming nothing the reader can search
    the repo for.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*]+", "", text)
    text = re.sub(r"(?<![\w_])_{1,2}(?=\S)|(?<=\S)_{1,2}(?![\w_])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _headline(text: str) -> str:
    """A bullet's bold lead-in, else its first sentence, clipped to one line."""
    lead_in = _LEAD_IN.match(text)
    head = _plain(lead_in.group(1) if lead_in else text.split(". ")[0])
    head = head.rstrip(" .:-")
    if len(head) <= TEASER_CHARS:
        return head
    return head[:TEASER_CHARS - 1].rstrip() + "\u2026"


def teaser(body: str) -> dict:
    """A section reduced to ``{alert, buckets: [{title, items, more}], more}``.

    Fenced blocks go whole: a one-time setup command is the reason to open the
    release page, not something to reprint in a listing. A GitHub alert is the
    one thing read out of order, since a section leads with it exactly when it
    carries something to do before upgrading. A bucket with no bullets falls back
    to its opening paragraph, which is the whole of the sections written as a
    heading naming the change and prose explaining it.
    """
    alert, buckets, fenced = "", [], False
    cur: dict | None = None

    def bucket(title: str = "") -> dict:
        buckets.append(fresh := {"title": title, "items": [], "para": ""})
        return fresh

    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith(">"):
            quoted = line.lstrip("> ").strip()
            if quoted and not _ALERT.match(quoted) and not alert:
                alert = _headline(quoted)
            continue
        if heading := _HEADING.match(line):
            cur = bucket(_plain(heading.group(1)))
            continue
        if not line.strip():
            continue
        cur = cur or bucket()
        if bullet := _BULLET.match(line):
            cur["items"].append(_headline(bullet.group(1)))
        elif not cur["items"] and not cur["para"]:
            cur["para"] = _headline(line)

    kept = []
    for b in buckets:
        items = b["items"][:TEASER_ITEMS] or ([b["para"]] if b["para"] else [])
        if not items:
            continue
        entry = {"title": b["title"], "items": items}
        if len(b["items"]) > TEASER_ITEMS:
            entry["more"] = len(b["items"]) - TEASER_ITEMS
        kept.append(entry)

    out = {}
    if alert:
        out["alert"] = alert
    if kept:
        out["buckets"] = kept[:TEASER_BUCKETS]
        if len(kept) > TEASER_BUCKETS:
            out["more"] = len(kept) - TEASER_BUCKETS
    return out


def draft(changes, since: str | None) -> str:
    """A worksheet for this release's notes, built from the commits in it.

    Deliberately not finished notes. A commit subject is written for someone
    reading the history of this repo; a changelog line is written for someone
    *using* it, and no rewrite of the first produces the second. What this
    removes is the blank page and the file mechanics — which is where the cost
    actually was — while leaving the writing to whoever can do it.

    The `Unsorted` bucket is the worksheet: `staged` refuses to publish a
    section that still has one, so the sorting can't be skipped by accident."""
    span = f"the {len(changes)} commits since {since}" if since \
        else f"all {len(changes)} commits, on a repo that has not released before"
    lines = [
        f"{DRAFT_MARKER} from {span}.",
        "     Move each line below into the section that applies and rewrite it for",
        "     someone *using* this, then delete this comment and the Unsorted",
        "     heading. -->",
        "",
        "### Added",
        "",
        "### Changed",
        "",
        "### Fixed",
        "",
        UNSORTED,
        "",
    ]
    for c in changes:
        ref = f"{c.sha}, #{c.pr}" if c.pr else c.sha
        lines.append(f"- {c.subject} ({ref})")
    return "\n".join(lines)


def staged_body(root: str | pathlib.Path | None = None) -> str | None:
    """The leading `## Unreleased` section's content, `""` if it has none, or
    None when there is no such section.

    `staged` is the same read with the release's demands attached — it refuses an
    empty section and a worksheet. This one reports the file's state without
    judging it, which is what decides whether there are notes to write or notes
    to publish."""
    path = _changelog(root)
    lines = path.read_text().splitlines()
    idx = _staged_index(lines)
    if idx is None:
        return None
    return "\n".join(lines[idx + 1:_section_end(lines, idx)]).strip()


def write_staged(body: str, root: str | pathlib.Path | None = None, *,
                 force: bool = False) -> None:
    """Put `body` under a leading `## Unreleased`, creating the heading if needed.

    Refuses a section that already has content unless `force`. Half-sorted notes
    are the case that matters: a worksheet with three of its lines moved up into
    `### Added` is work nobody can recover if a re-run drops a fresh worksheet on
    top of it."""
    existing = staged_body(root)
    if existing and not force:
        raise SystemExit(
            "shipyard: CHANGELOG.md's `## Unreleased` section already has content. "
            "Finish it and release, or pass --draft to replace it with a fresh "
            "worksheet.")
    path = _changelog(root)
    lines = path.read_text().splitlines()
    idx = _staged_index(lines)
    if idx is None:
        # Before the first released section, so the newest release stays at the
        # top; on a changelog with no sections at all, at the end of the preamble.
        idx = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
        lines[idx:idx] = ["## Unreleased", ""]
    end = _section_end(lines, idx)
    lines[idx + 1:end] = ["", body.strip(), ""]
    path.write_text("\n".join(lines).rstrip() + "\n")
