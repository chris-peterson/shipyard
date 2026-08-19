"""Emit the plugin.yml suite: block as docs/plugin-docs.json.

The plugin's own doc site (and the bridge.ai session player) fetch plugin-docs.json
to hydrate the live session previews — the same suite: data the marketplace reads
from plugin.yml, so the hub and the docs preview never drift. docs/plugin-docs.json
is a render target (gitignored); regenerated on every docs build.
"""
from __future__ import annotations

import json
import pathlib

from ._common import block, load_plugin, plugin_root


def run(root: str | pathlib.Path | None = None) -> int:
    suite = block(load_plugin(root), "suite", "plugin.yml") or None
    if not suite:
        raise SystemExit("plugin.yml has no suite: block — the docs session preview needs it")
    generated = json.dumps(suite, indent=2, ensure_ascii=False) + "\n"
    target = plugin_root(root) / "docs" / "plugin-docs.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated)
    return 0
