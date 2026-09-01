"""Print the aggregator's roster as tab-separated ``name<TAB>url`` lines.

The aggregator's sync step needs the roster *before* any plugin is on disk, so it
can clone them. Reading it from plugins.yml — rather than from the generated
marketplace manifest — keeps that manifest purely downstream, and means the sync
step doesn't depend on a generated file being current.

``--include-retired`` adds the plugins the groups have retired. They are off the
roster, so no manifest names them, but the growth view reads what they shipped
out of their checkouts — which the sync step has to have cloned.
"""
from __future__ import annotations

import pathlib

from ._aggregate import retired, roster


def run(root: str | pathlib.Path | None = None, *,
        include_retired: bool = False) -> int:
    entries = roster(root) + (retired(root) if include_retired else [])
    for name, url in entries:
        print(f"{name}\t{url}")
    return 0
