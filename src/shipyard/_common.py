"""Shared helpers for the shipyard generators.

shipyard runs against a *target plugin repo* — the one whose sources it projects.
Every command resolves that repo's root the same way: an explicit ``--root``, or
the current working directory (which is how CI runs it, from the plugin
checkout). The per-plugin scripts this replaces resolved root from their own
file location; shipyard is external tooling, so root is always the target.
"""
from __future__ import annotations

import pathlib

import yaml


def plugin_root(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return pathlib.Path(root or pathlib.Path.cwd()).resolve()


def load_plugin(root: str | pathlib.Path | None = None) -> dict:
    """Parsed plugin.yml for the target repo. Missing/empty is an error — every
    shipyard command needs the canonical descriptor."""
    path = plugin_root(root) / "plugin.yml"
    if not path.exists():
        raise SystemExit(f"shipyard: no plugin.yml at {path}")
    return yaml.safe_load(path.read_text()) or {}
