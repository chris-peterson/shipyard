"""Shared helpers for the aggregate generators.

Most shipyard commands run against a single *plugin* repo. These run against an
*aggregator* — a repo whose job is to present a set of plugins (a marketplace, a
hub, a catalog site). Its canonical source is ``plugins.yml``, which declares
only what the aggregator itself owns: its identity, the roster, and the roster's
order. Everything shown *about* a plugin is read from that plugin's own
``plugin.yml``, so the two can't drift.

The spokes are sibling checkouts beside the aggregator, which is what the
aggregator's own sync step already produces::

    workspace/
      claude-marketplace/plugins.yml    <- the aggregator, shipyard's --root
      anchor/plugin.yml                 <- a spoke
      beacon/plugin.yml

``source:`` is a URL template rather than a per-entry field so the roster is
readable with no spokes on disk — that is what lets the sync step clone them in
the first place, and what keeps the generated marketplace manifest purely
downstream of the roster instead of doubling as its source.
"""
from __future__ import annotations

import csv
import pathlib
from collections.abc import Callable

from ._common import load_mapping, plugin_root

MANIFEST = "plugins.yml"

# Artifact categories, in the column order of the aggregator's artifact log.
CATS = ("skills", "rules", "hooks", "commands", "agents")
SINGULAR = {c: c[:-1] for c in CATS}          # skills -> skill
PLURAL = {v: k for k, v in SINGULAR.items()}  # skill  -> skills


def is_aggregate(root: str | pathlib.Path | None = None) -> bool:
    return (plugin_root(root) / MANIFEST).exists()


def load_manifest(root: str | pathlib.Path | None = None) -> dict:
    """Parsed plugins.yml for the target aggregator. Missing/empty is an error —
    every aggregate command needs the roster."""
    path = plugin_root(root) / MANIFEST
    if not path.exists():
        raise SystemExit(f"shipyard: no {MANIFEST} at {path}")
    return load_mapping(path, "a mapping carrying the roster")


def source_url(manifest: dict) -> Callable[[str], str]:
    """A resolver from a plugin name to its repository URL, per ``source:``.

    Takes any name rather than only a rostered one: the template is where the
    aggregator says its plugins live, and a retired plugin still lives there.
    """
    template = manifest.get("source")
    if not template:
        raise SystemExit(
            f"shipyard: {MANIFEST} has no source: — the roster needs a URL template "
            "(e.g. https://github.com/{owner}/{name}.git) to be resolvable without "
            "the plugin checkouts")
    owner = manifest.get("owner")
    substitutions = {"owner": owner} if owner else {}

    def url(name: str) -> str:
        try:
            return template.format(name=name, **substitutions)
        except KeyError as exc:
            field = exc.args[0]
            raise SystemExit(
                f"shipyard: {MANIFEST} source: references {{{field}}}, "
                f"but no {field}: is declared") from None

    return url


def roster(root: str | pathlib.Path | None = None) -> list[tuple[str, str]]:
    """The declared plugins as ``(name, source_url)`` pairs, in declared order.

    Reads only plugins.yml — no spoke checkout required.

    The roster is hand-written, and every malformed shape it can take produces a
    plausible-looking result rather than an obvious one: a scalar `plugins:`
    iterates its characters, a mapping entry formats into the URL, an undeclared
    `{owner}` leaves an empty path segment. Each is rejected here, because the
    symptom otherwise surfaces much later as a confusing error about a plugin
    nobody wrote down — or as a published catalog that is quietly wrong."""
    manifest = load_manifest(root)
    url = source_url(manifest)
    names = manifest.get("plugins")
    if not names:
        raise SystemExit(f"shipyard: {MANIFEST} declares no plugins:")
    if not isinstance(names, list):
        raise SystemExit(
            f"shipyard: {MANIFEST} plugins: must be a list of names, "
            f"got a {type(names).__name__}")
    for entry in names:
        if not isinstance(entry, str):
            raise SystemExit(
                f"shipyard: {MANIFEST} plugins: takes plain names, but got {entry!r} — "
                "a plugin's own plugin.yml carries everything else about it")
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise SystemExit(
            f"shipyard: {MANIFEST} lists {', '.join(repeated)} more than once")

    return [(n, url(n)) for n in names]


def retired(root: str | pathlib.Path | None = None) -> list[tuple[str, str]]:
    """Plugins the groups have retired, as ``(name, source_url)`` pairs.

    A retired plugin is off the roster, so nothing about the marketplace it
    publishes mentions it — but the aggregator's history still covers what it
    shipped, and that is read from its checkout like any other. So the sync step
    needs its URL, resolved through the same template the roster uses.
    """
    names = [n for g in groups(root) for n in g["retired"]]
    if not names:
        return []
    url = source_url(load_manifest(root))
    return [(n, url(n)) for n in names]


def workspace(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return plugin_root(root).parent


def load_spoke(name: str, root: str | pathlib.Path | None = None) -> dict:
    """Parsed plugin.yml for one rostered plugin, from its sibling checkout.

    A rostered plugin with no readable descriptor is a hard error: the aggregate
    artifacts are projections of the spokes, so a missing one would silently
    publish an incomplete catalog."""
    path = workspace(root) / name / "plugin.yml"
    if not path.exists():
        raise SystemExit(
            f"shipyard: {name} is on the roster but has no plugin.yml at {path} — "
            "sync the plugin checkouts beside the aggregator first")
    spec = load_mapping(path, "a mapping of the plugin's fields")
    if not spec.get("description"):
        raise SystemExit(f"shipyard: {name}/plugin.yml has no description:")
    return spec


def load_spokes(root: str | pathlib.Path | None = None) -> dict[str, dict]:
    """Every rostered plugin's descriptor, keyed by name, in roster order."""
    return {name: load_spoke(name, root) for name, _ in roster(root)}


def as_object(value: object) -> object:
    """plugin.yml writes author/owner as a plain string; the JSON manifests want
    an object. Anything already structured passes through."""
    return {"name": value} if isinstance(value, str) else value


def groups(root: str | pathlib.Path | None = None) -> list[dict]:
    """The catalog's functional-area groups, in declared order.

    A group declares its identity and how it presents: ``key``, the ``accent``
    CSS custom property its cards and chart bands take their color from, and the
    ``tag`` the catalog labels it with. Membership is deliberately not here — a
    plugin's own plugin.yml names the group it belongs to (``suite.group``), and
    restating that beside the roster is the drift the split exists to prevent.

    ``retired:`` is the exception, and only because its subjects have no spoke to
    read: a plugin off the roster still shipped what it shipped, so it keeps the
    group and the slot it held while it was on it.
    """
    declared = load_manifest(root).get("groups")
    if not declared:
        return []
    if not isinstance(declared, list):
        raise SystemExit(
            f"shipyard: {MANIFEST} groups: must be a list of groups, "
            f"got a {type(declared).__name__}")
    out, seen = [], set()
    for entry in declared:
        if not isinstance(entry, dict) or not entry.get("key"):
            raise SystemExit(
                f"shipyard: {MANIFEST} groups: takes mappings with a key:, "
                f"but got {entry!r}")
        key = entry["key"]
        if key in seen:
            raise SystemExit(f"shipyard: {MANIFEST} declares the group {key} more than once")
        seen.add(key)
        retired = entry.get("retired") or []
        if not isinstance(retired, list):
            raise SystemExit(
                f"shipyard: {MANIFEST} group {key} retired: must be a list of names, "
                f"got a {type(retired).__name__}")
        out.append({"key": key, "accent": entry.get("accent", ""),
                    "tag": entry.get("tag", ""), "retired": list(retired)})
    return out


def grouped(root: str | pathlib.Path | None = None) -> list[tuple[str, str, int]]:
    """``(plugin, group_key, shade)`` for every plugin the groups place, in
    catalog order: each group's rostered plugins in roster order, then the
    plugins it has retired.

    ``shade`` is the plugin's index within its group, which is what lets two
    cards in one group take distinguishable steps of the group's one accent
    rather than needing a color each.

    A rostered plugin whose ``suite.group`` names no declared group is an error.
    That check has to live here: it is the one place that holds both the roster's
    declarations and the groups', and a plugin missing from every group is a
    plugin the catalog silently would not render.
    """
    declared = groups(root)
    if not declared:
        return []
    keys = {g["key"] for g in declared}
    members: dict[str, list[str]] = {g["key"]: [] for g in declared}
    for name, spec in load_spokes(root).items():
        key = (spec.get("suite") or {}).get("group")
        if not key:
            raise SystemExit(
                f"shipyard: {name}/plugin.yml has no suite.group: — "
                f"{MANIFEST} groups the catalog by it")
        if key not in keys:
            raise SystemExit(
                f"shipyard: {name}/plugin.yml names the group {key!r}, which "
                f"{MANIFEST} does not declare (has {', '.join(sorted(keys))})")
        members[key].append(name)
    placed = []
    for g in declared:
        for shade, name in enumerate(members[g["key"]] + g["retired"]):
            placed.append((name, g["key"], shade))
    return placed


# ---- the artifact log --------------------------------------------------------
# An aggregator may keep a rolling log of each plugin's named artifacts, written
# from the plugins' git state by the aggregator's own recorder. It is a change
# log, not a snapshot: each row carries +/- tokens, and the current member set is
# whatever replaying the file in order produces. Declaring the log in plugins.yml
# (`artifacts:`) is what opts an aggregator into component data.
#
# shipyard reads the log; the aggregator's recorder writes it. change_tokens is
# the encode half, kept here beside its decode so the round-trip the whole
# history depends on is one testable pair.


def empty_members() -> dict[str, set]:
    return {c: set() for c in CATS}


def apply_tokens(members: dict[str, set], change: str) -> None:
    """Apply a change string's +/- tokens to a member set, in place. Tokens that
    don't parse as +/-cat:name are ignored, so hand-edits stay robust."""
    for tok in change.split():
        if len(tok) < 2 or tok[0] not in "+-" or ":" not in tok:
            continue
        singular, name = tok[1:].split(":", 1)
        cat = PLURAL.get(singular)
        if cat:
            members[cat].add(name) if tok[0] == "+" else members[cat].discard(name)


def change_tokens(prev: dict[str, set], cur: dict[str, set]) -> str:
    """Named +/- tokens for the move from prev to cur, e.g.
    '+skill:resolve-feedback -skill:address-feedback'."""
    parts = []
    for c in CATS:
        parts += [f"+{SINGULAR[c]}:{n}" for n in sorted(cur[c] - prev[c])]
        parts += [f"-{SINGULAR[c]}:{n}" for n in sorted(prev[c] - cur[c])]
    return " ".join(parts)


def replay(rows: list[dict]) -> dict[str, dict[str, set]]:
    """Reconstruct each plugin's current member set by applying every row's
    change tokens in file order — so the recorder needs no state file and never
    re-walks git history."""
    state: dict[str, dict[str, set]] = {}
    for r in rows:
        apply_tokens(state.setdefault(r["plugin"], empty_members()), r["change"])
    return state


def components(root: str | pathlib.Path | None = None) -> dict[str, dict[str, list[str]]]:
    """Each plugin's current named artifacts by category, from the replayed log.

    Empty when plugins.yml declares no ``artifacts:`` log. Empty categories are
    dropped so a consumer renders only what a plugin actually has."""
    declared = load_manifest(root).get("artifacts")
    if not declared:
        return {}
    path = plugin_root(root) / declared
    if not path.exists():
        raise SystemExit(f"shipyard: {MANIFEST} declares artifacts: {declared}, but {path} is missing")
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {
        name: {c: sorted(members[c]) for c in CATS if members[c]}
        for name, members in replay(rows).items()
    }
