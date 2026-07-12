"""Shared helpers for the shipyard generators.

shipyard runs against a *target plugin repo* — the one whose sources it projects.
Every command resolves that repo's root the same way: an explicit ``--root``, or
the current working directory (which is how CI runs it, from the plugin
checkout). The per-plugin scripts this replaces resolved root from their own
file location; shipyard is external tooling, so root is always the target.
"""
from __future__ import annotations

import difflib
import pathlib

import yaml


def plugin_root(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return pathlib.Path(root or pathlib.Path.cwd()).resolve()


def diff(target: pathlib.Path, current: str, generated: str,
         root: str | pathlib.Path | None = None) -> str:
    """A git-style unified diff of the committed artifact vs. what the generator
    would write. Empty string when they already match. Used by preview mode to
    show what the next `generate` (at release) will apply — never to fail a
    build. `target` is labelled by its path relative to the plugin root."""
    if current == generated:
        return ""
    try:
        rel = target.relative_to(plugin_root(root)).as_posix()
    except ValueError:
        rel = target.name
    return "".join(difflib.unified_diff(
        current.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    ))


def load_plugin(root: str | pathlib.Path | None = None) -> dict:
    """Parsed plugin.yml for the target repo. Missing/empty is an error — every
    shipyard command needs the canonical descriptor."""
    path = plugin_root(root) / "plugin.yml"
    if not path.exists():
        raise SystemExit(f"shipyard: no plugin.yml at {path}")
    return yaml.safe_load(path.read_text()) or {}
