"""Project plugin.yml → .claude-plugin/plugin.json.

plugin.yml is the canonical descriptor; plugin.json is generated and committed
(Claude Code reads the committed file at install). ``--check`` verifies the
committed file is in sync (CI gate / pre-commit hook).
"""
from __future__ import annotations

import json
import pathlib

from ._common import load_plugin, plugin_root

# plugin.json carries only the packaging fields, in this order. The rest of
# plugin.yml (marketplace:, suite:) projects into other targets, not here.
PACKAGING_FIELDS = (
    "name",
    "version",
    "description",
    "author",
    "repository",
    "icon",
    "license",
    "keywords",
    "homepage",
)


def build(root: str | pathlib.Path | None = None) -> str:
    spec = load_plugin(root)
    out = {}
    for field in PACKAGING_FIELDS:
        value = spec.get(field)
        # homepage lives under the marketplace: block in plugin.yml, but Claude
        # Code reads it from plugin.json, so project it here too.
        if field == "homepage" and value is None:
            value = (spec.get("marketplace") or {}).get("homepage")
        if value is None:
            continue
        # author is a plain string in plugin.yml; plugin.json wants an object.
        if field == "author" and isinstance(value, str):
            value = {"name": value}
        out[field] = value
    return json.dumps(out, indent=2) + "\n"


def run(root: str | pathlib.Path | None = None, check: bool = False) -> int:
    generated = build(root)
    target = plugin_root(root) / ".claude-plugin" / "plugin.json"
    if check:
        current = target.read_text() if target.exists() else ""
        if current != generated:
            raise SystemExit(
                f"{target} is out of sync with plugin.yml.\n"
                "Run `shipyard gen-plugin-json` and commit the result."
            )
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated)
    return 0
