"""Project the rostered plugins' declared dependencies → docs/deps.json.

Edges are *declared* in each plugin.yml (`suite.dependencies`, a list of
`{name, required, reason}`), never discovered — taking on a dependency is an
intentional act, so the graph is a direct projection with no code scan and no
drift heuristic.

An edge may point at a plugin the roster doesn't carry: a plugin can support an
optional backend the marketplace doesn't ship. Those stay in `edges` while
`nodes` stays the roster, which is how the graph distinguishes the catalog from
everything it merely talks to.

docs/deps.json is a render target — regenerated on every docs build, not committed.
"""
from __future__ import annotations

import json
import pathlib

from ._aggregate import load_spokes
from ._common import plugin_root


def build(root: str | pathlib.Path | None = None) -> str:
    spokes = load_spokes(root)
    edges = [
        {
            "from": name,
            "to": dep["name"],
            "required": bool(dep.get("required", False)),
            "reason": dep.get("reason", ""),
        }
        for name, spec in spokes.items()
        for dep in (spec.get("suite") or {}).get("dependencies") or []
    ]
    graph = {"nodes": list(spokes), "edges": edges}
    return json.dumps(graph, indent=2, ensure_ascii=False) + "\n"


def run(root: str | pathlib.Path | None = None) -> int:
    target = plugin_root(root) / "docs" / "deps.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build(root))
    return 0
