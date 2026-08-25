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

from . import _validate
from ._aggregate import MANIFEST, as_object, load_manifest, load_spoke, roster
from ._common import plugin_root

SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"

# The marketplace's own identity — the only fields it can't read off a plugin.
IDENTITY_FIELDS = ("name", "description", "owner")

# The marketplaces this one's plugins may depend on. Claude Code refuses to
# auto-install a dependency from anywhere else, so the allowlist belongs to the
# marketplace rather than to any plugin — plugins.yml carries it under the same
# name the manifest publishes it under.
CROSS_MARKETPLACE = "allowCrossMarketplaceDependenciesOn"


def _entry(name: str, url: str, root: str | pathlib.Path | None,
           allowed: set[str]) -> dict:
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

    # relevance is read from the marketplace entry, so this is the one file it
    # can reach Claude Code through.
    if "relevance" in marketplace:
        _validate.raise_if(
            _validate.relevance_errors(marketplace["relevance"]),
            f"{name}/plugin.yml declares a relevance block Claude Code would "
            f"load and never match on:")
        entry["relevance"] = marketplace["relevance"]

    # The dependencies themselves project into the plugin's own plugin.json;
    # what only the aggregator can settle is whether a cross-marketplace one is
    # allowlisted here.
    if "dependencies" in spec:
        _validate.raise_if(
            _validate.dependency_errors(spec["dependencies"], name, allowed),
            f"{name}/plugin.yml declares dependencies Claude Code cannot resolve:")
    return entry


def build(root: str | pathlib.Path | None = None) -> str:
    manifest = load_manifest(root)
    missing = [f for f in IDENTITY_FIELDS if not manifest.get(f)]
    if missing:
        raise SystemExit(f"shipyard: {MANIFEST} is missing {', '.join(missing)}")
    allowed = manifest.get(CROSS_MARKETPLACE) or []
    if not isinstance(allowed, list) or not all(
            isinstance(m, str) and m for m in allowed):
        raise SystemExit(
            f"shipyard: {MANIFEST} {CROSS_MARKETPLACE}: must be a list of "
            f"marketplace names")
    out = {
        "$schema": SCHEMA,
        "name": manifest["name"],
        "description": manifest["description"],
        "owner": as_object(manifest["owner"]),
    }
    if allowed:
        out[CROSS_MARKETPLACE] = allowed
    out["plugins"] = [_entry(name, url, root, set(allowed))
                      for name, url in roster(root)]
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def _target(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return plugin_root(root) / ".claude-plugin" / "marketplace.json"


def run(root: str | pathlib.Path | None = None) -> int:
    generated = build(root)
    target = _target(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated)
    return 0
