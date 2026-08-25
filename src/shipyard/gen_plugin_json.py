"""Project plugin.yml → .claude-plugin/plugin.json.

plugin.yml is the canonical descriptor; plugin.json is generated and committed
(Claude Code reads the committed file at install).
"""
from __future__ import annotations

import json
import pathlib

from . import _validate
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
    "dependencies",
)


def build(root: str | pathlib.Path | None = None) -> str:
    spec = load_plugin(root)
    if "dependencies" in spec:
        # Only the aggregator can see allowCrossMarketplaceDependenciesOn, so a
        # dependency's marketplace: is cross-checked there, not here.
        _validate.raise_if(
            _validate.dependency_errors(spec["dependencies"], spec.get("name", "")),
            "plugin.yml declares dependencies Claude Code cannot resolve:")
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


def _target(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return plugin_root(root) / ".claude-plugin" / "plugin.json"


def run(root: str | pathlib.Path | None = None) -> int:
    generated = build(root)
    target = _target(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated)
    return 0
