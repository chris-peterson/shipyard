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


def load_mapping(path: pathlib.Path, shape: str) -> dict:
    """Parsed YAML from ``path``, required to be a mapping at its top level.

    ``yaml.safe_load(...) or {}`` reads an empty file as an empty mapping, which is
    right, but says nothing about a file whose top level is the wrong *type*. That
    then fails wherever a generator first dereferences it, as an AttributeError
    naming a line of shipyard rather than the file the reader has to fix.

    ``shape`` describes the correct top level, because whoever sees this has
    shipyard's source nowhere in reach: it lands in a CI log, or in a plugin
    author's terminal running the CLI over their own repo."""
    doc = yaml.safe_load(path.read_text())
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise SystemExit(
            f"shipyard: {path} must be {shape}, but its top level is "
            f"a {type(doc).__name__}")
    return doc


def block(spec: dict, key: str, source: str) -> dict:
    """A ``spec`` block that has to be a mapping when it's present.

    Same failure as a wrong-typed file, one level in: `docs:` written as a list
    reaches a `.get` somewhere downstream instead of being reported here."""
    value = spec.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SystemExit(
            f"shipyard: {source} `{key}:` must be a mapping, but it is "
            f"a {type(value).__name__}")
    return value


def load_plugin(root: str | pathlib.Path | None = None) -> dict:
    """Parsed plugin.yml for the target repo. Missing/empty is an error — every
    shipyard command needs the canonical descriptor."""
    path = plugin_root(root) / "plugin.yml"
    if not path.exists():
        raise SystemExit(f"shipyard: no plugin.yml at {path}")
    return load_mapping(path, "a mapping of the plugin's fields")
