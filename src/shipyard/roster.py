"""Print the aggregator's roster as tab-separated ``name<TAB>url`` lines.

The aggregator's sync step needs the roster *before* any plugin is on disk, so it
can clone them. Reading it from plugins.yml — rather than from the generated
marketplace manifest — keeps that manifest purely downstream, and means the sync
step doesn't depend on a generated file being current.
"""
from __future__ import annotations

import pathlib

from ._aggregate import roster


def run(root: str | pathlib.Path | None = None) -> int:
    for name, url in roster(root):
        print(f"{name}\t{url}")
    return 0
