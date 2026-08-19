"""Project plugins.yml + the rostered plugins' plugin.yml → .claude-plugin/marketplace.json.

The roster says which plugins the marketplace ships and in what order; each
plugin's own plugin.yml says what it is. Claude Code reads the committed
marketplace.json at `marketplace add`, so it is generated and committed — the same
source → generated split as plugin.yml → plugin.json, one level up.

Nothing about a plugin is restated here. A description edited in the plugin's
repo reaches the marketplace by regenerating, not by a second hand-edit.
"""
from __future__ import annotations

import json
import pathlib

from ._aggregate import MANIFEST, as_object, load_manifest, load_spoke, roster
from ._common import plugin_root

SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"

# The marketplace's own identity — the only fields it can't read off a plugin.
IDENTITY_FIELDS = ("name", "description", "owner")


def _entry(name: str, url: str, root: str | pathlib.Path | None) -> dict:
    spec = load_spoke(name, root)
    marketplace = spec.get("marketplace") or {}
    entry = {
        "name": name,
        "description": spec["description"],
        "author": as_object(spec.get("author")),
        "source": {"source": "url", "url": url},
    }
    # category and homepage are optional in the marketplace schema; a plugin that
    # declares neither simply publishes without them.
    for field in ("category", "homepage"):
        if marketplace.get(field):
            entry[field] = marketplace[field]
    if entry["author"] is None:
        del entry["author"]
    return entry


def build(root: str | pathlib.Path | None = None) -> str:
    manifest = load_manifest(root)
    missing = [f for f in IDENTITY_FIELDS if not manifest.get(f)]
    if missing:
        raise SystemExit(f"shipyard: {MANIFEST} is missing {', '.join(missing)}")
    out = {
        "$schema": SCHEMA,
        "name": manifest["name"],
        "description": manifest["description"],
        "owner": as_object(manifest["owner"]),
        "plugins": [_entry(name, url, root) for name, url in roster(root)],
    }
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def _target(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return plugin_root(root) / ".claude-plugin" / "marketplace.json"


def run(root: str | pathlib.Path | None = None) -> int:
    generated = build(root)
    target = _target(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated)
    return 0
