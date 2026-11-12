"""``shipyard list``: what a marketplace ships, read from its published catalog.

The default source is bridge.ai's live site, so the answer is what users can
install right now rather than what a local checkout happens to hold. ``--root``
builds the same catalog from an aggregator checkout instead — the read for a
change that hasn't deployed yet, and the one that works offline.

Human-readable by default; ``--json`` prints the entries as the catalog
publishes them, so a script gets every field rather than the table's selection.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import urllib.error
import urllib.request

from .gen_catalog_json import SCHEMA

DEFAULT_URL = "https://chris-peterson.github.io/claude-marketplace/catalog.json"
TYPES = ("marketplace", "plugin")

# Singular forms for the contents column, in the order it lists them.
NOUNS = {"plugins": "plugin", "skills": "skill", "rules": "rule", "hooks": "hook",
         "commands": "command", "agents": "agent"}


def fetch(url: str, timeout: float = 15) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "shipyard"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        hint = (" — the site may predate catalog.json; redeploy it, or pass --root "
                "<marketplace checkout>") if exc.code == 404 else ""
        raise SystemExit(f"shipyard list: {url}: HTTP {exc.code}{hint}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SystemExit(f"shipyard list: couldn't reach {url}: {reason}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"shipyard list: {url} isn't JSON: {exc}") from None


def load(root: str | pathlib.Path | None, url: str | None) -> dict:
    if root is not None:
        from .gen_catalog_json import build_data
        return build_data(root)
    catalog = fetch(url or DEFAULT_URL)
    if not isinstance(catalog, dict) or catalog.get("schema") != SCHEMA:
        raise SystemExit(
            f"shipyard list: {url or DEFAULT_URL} is catalog schema "
            f"{catalog.get('schema') if isinstance(catalog, dict) else '?'}, "
            f"and this shipyard reads schema {SCHEMA} — update shipyard")
    return catalog


def contents(entry: dict) -> str:
    parts = []
    for key, noun in NOUNS.items():
        n = (entry.get("counts") or {}).get(key)
        if n:
            parts.append(f"{n} {noun}{'' if n == 1 else 's'}")
    if entry.get("cli"):
        parts.append("cli")
    return ", ".join(parts)


def table(catalog: dict, entries: list[dict], *, width: int | None) -> str:
    header = ("TYPE", "NAME", "CATEGORY", "VERSION", "CONTENTS", "DESCRIPTION")
    rows = [(e["type"], e["name"], e.get("category") or "-", e.get("version") or "-",
             contents(e), e.get("description") or "") for e in entries]
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(5)]

    def line(row: tuple[str, ...]) -> str:
        text = "  ".join(cell.ljust(w) for cell, w in zip(row, widths)) + "  " + row[5]
        if width and len(text) > width:
            text = text[:max(width - 1, 0)].rstrip() + "…"
        return text.rstrip()

    return "\n".join([catalog.get("title", ""), "", line(header), *map(line, rows)])


def run(root: str | pathlib.Path | None = None, *, url: str | None = None,
        as_json: bool = False, type_: str | None = None) -> int:
    catalog = load(root, url)
    entries = [e for e in catalog.get("entries", []) if not type_ or e.get("type") == type_]
    if as_json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0
    # Clip the description to the terminal; a pipe gets every word.
    width = shutil.get_terminal_size().columns if sys.stdout.isatty() else None
    print(table(catalog, entries, width=width))
    return 0
