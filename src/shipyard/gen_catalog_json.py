"""Project an aggregator's roster → docs/catalog.json, the catalog in machine-readable form.

The doc site's own data (``plugins.js``) is shaped for the page that renders it:
a JavaScript global, keyed for the cards. ``catalog.json`` is the same catalog for
a program to read — ``shipyard list`` fetches it from the live site — so it is
plain JSON, one flat list of typed entries, and versioned by ``schema`` so a
reader can tell a shape it doesn't know from a catalog that is simply empty.

An entry is the marketplace itself (``type: marketplace``) or one of the plugins
it ships (``type: plugin``), in roster order. Everything about a plugin is read
from its own ``plugin.yml``, the same as every other aggregate projection; the
components are replayed from the artifact log the roster declares, so a plugin's
list of skills can't name one it no longer ships.

docs/catalog.json is a render target — regenerated on every docs build, not committed.
"""
from __future__ import annotations

import json
import pathlib

from ._aggregate import CATS, MANIFEST, components, load_manifest, load_spoke, roster
from ._common import plugin_root

SCHEMA = 1

# The artifact log records hooks.json itself as a hook named `hooks` — the wiring
# file, not a hook anyone wrote. A count of a plugin's hooks shouldn't include it.
WIRING = {"hooks": {"hooks"}}


def _components(named: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {}
    for cat in CATS:
        names = [n for n in named.get(cat, []) if n not in WIRING.get(cat, set())]
        if names:
            out[cat] = names
    return out


def _plugin(name: str, url: str, named: dict[str, list[str]],
            root: str | pathlib.Path | None) -> dict:
    spec = load_spoke(name, root)
    marketplace = spec.get("marketplace") or {}
    parts = _components(named)
    return {
        "type": "plugin",
        "name": name,
        "category": marketplace.get("category"),
        "version": str(spec["version"]) if "version" in spec else None,
        "description": spec["description"],
        "cli": bool((spec.get("suite") or {}).get("cli")) or "cli" in spec,
        "counts": {cat: len(names) for cat, names in parts.items()},
        "components": parts,
        "repository": spec.get("repository") or url,
        "homepage": marketplace.get("homepage"),
    }


def build_data(root: str | pathlib.Path | None = None) -> dict:
    manifest = load_manifest(root)
    if not manifest.get("name"):
        raise SystemExit(f"shipyard: {MANIFEST} has no name:")
    named = components(root)
    plugins = [_plugin(name, url, named.get(name, {}), root) for name, url in roster(root)]
    title = manifest.get("title") or manifest["name"]
    marketplace = {
        "type": "marketplace",
        "name": manifest["name"],
        "category": None,
        "version": None,
        "description": manifest.get("description"),
        "counts": {"plugins": len(plugins)},
    }
    return {"schema": SCHEMA, "title": title, "entries": [marketplace, *plugins]}


def build(root: str | pathlib.Path | None = None) -> str:
    return json.dumps(build_data(root), indent=2, ensure_ascii=False) + "\n"


def run(root: str | pathlib.Path | None = None) -> int:
    target = plugin_root(root) / "docs" / "catalog.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build(root))
    return 0
