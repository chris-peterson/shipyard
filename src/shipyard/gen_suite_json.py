"""Emit the plugin.yml suite: block as docs/suite.json.

The plugin's own doc site (and the bridge.ai session player) fetch suite.json to
hydrate the live session previews — the same suite: data the marketplace reads
from plugin.yml, so the hub and the docs preview never drift. docs/suite.json is
a render target (gitignored); regenerated on every docs build.
"""
from __future__ import annotations

import json
import pathlib

from ._common import load_plugin, plugin_root


def run(root: str | pathlib.Path | None = None, check: bool = False) -> int:
    suite = load_plugin(root).get("suite")
    if not suite:
        raise SystemExit("plugin.yml has no suite: block — the docs session preview needs it")
    generated = json.dumps(suite, indent=2, ensure_ascii=False) + "\n"
    target = plugin_root(root) / "docs" / "suite.json"
    if check:
        current = target.read_text() if target.exists() else ""
        if current != generated:
            raise SystemExit(f"{target} is out of sync with plugin.yml (run `shipyard gen-suite-json`).")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated)
    return 0
