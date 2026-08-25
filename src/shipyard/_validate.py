"""Reject the relevance and dependency shapes Claude Code accepts and then ignores.

Both blocks are read by Claude Code alone, and neither reports back. A plugin
whose signal name is misspelled makes every suggestion it would have made and
tells nobody; a dependency whose `version` is not a semver range resolves to
nothing until someone tries to install it. `claude plugin validate --strict`
catches part of this and is worth running — it errors on an empty `signals`, a
hostname carrying a scheme, an uncompilable regex, and a cap overrun, and warns
on a misspelled signal name. It passes an invalid `version` range, a misspelled
key on a dependency object, and a cross-marketplace dependency the root
marketplace never allowlisted.

The caps and the field semantics come from the upstream field reference:
https://code.claude.com/docs/en/plugin-relevance
https://code.claude.com/docs/en/plugin-dependencies
"""
from __future__ import annotations

import re

RELEVANCE_FIELDS = ("topic", "signals")
TOPIC_MAX = 64

# Per-signal caps: (max entries, max length of one entry). manifestDeps counts
# objects, so its second element applies to each regex inside one.
SIGNAL_CAPS = {
    "cwd": (10, 256),
    "cli": (10, 64),
    "hosts": (20, 128),
    "filesRead": (10, 256),
    "manifestDeps": (10, 256),
}

MANIFEST_DEP_FIELDS = ("file", "pattern")
DEPENDENCY_FIELDS = ("name", "version", "marketplace")

# A bare lowercase hostname: what Claude Code's own validator calls the only
# acceptable `hosts` entry, no scheme, port, or path.
HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")

# One version, possibly partial and possibly wildcarded: 1, 1.2, 1.2.3, 1.x, *.
_PARTIAL = re.compile(
    r"^v?(?:\d+|[xX*])"
    r"(?:\.(?:\d+|[xX*])"
    r"(?:\.(?:\d+|[xX*]))?)?"
    r"(?:-[0-9A-Za-z.-]+)?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)
# The operators npm recognizes. `~>` is Ruby's and resolves to nothing here, so
# it is deliberately absent: it parses as `~` against a leftover `>2.1.0`.
_COMPARATOR = re.compile(r"^(<=|>=|<|>|=|~|\^)?(.+)$")


def _is_version(text: str) -> bool:
    return bool(_PARTIAL.match(text.strip()))


def _is_comparator_set(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if " - " in text:
        low, _, high = text.partition(" - ")
        return _is_version(low) and _is_version(high)
    # npm allows a space after the operator (">= 1.2.3"), so close it up before
    # splitting on whitespace — otherwise the operator parses as its own token.
    text = re.sub(r"(<=|>=|<|>|=|~|\^)\s+", r"\1", text)
    for token in text.split():
        match = _COMPARATOR.match(token)
        if not match or not _is_version(match.group(2)):
            return False
    return True


def is_semver_range(value: str) -> bool:
    """Whether `value` parses as an npm semver range.

    An empty string is npm's "any version", but as a *declared* constraint it is
    a field somebody meant to fill, so it is not accepted here.
    """
    return bool(value.strip()) and all(
        _is_comparator_set(part) for part in value.split("||"))


def _at(where: str, field: str) -> str:
    return f"{where}/{field}" if where else f"/{field}"


def _string_entries(entries: list, signal: str, where: str) -> list[str]:
    """Errors for one string-valued signal array (everything but manifestDeps)."""
    _, max_length = SIGNAL_CAPS[signal]
    errors = []
    for i, entry in enumerate(entries):
        at = f"{where}/{i}"
        if not isinstance(entry, str) or not entry:
            errors.append(f"{at} must be a non-empty string")
            continue
        if len(entry) > max_length:
            errors.append(f"{at} is longer than {max_length} characters")
        if signal == "hosts" and not HOSTNAME.match(entry):
            errors.append(
                f"{at} must be a bare lowercase hostname, with no scheme, port, "
                f"or path: {entry!r}")
    duplicates = sorted({e for e in entries if entries.count(e) > 1
                         if isinstance(e, str)})
    for entry in duplicates:
        errors.append(f"{where} lists {entry!r} more than once")
    return errors


def _manifest_deps(entries: list, where: str) -> list[str]:
    errors = []
    for i, dep in enumerate(entries):
        at = f"{where}/{i}"
        if not isinstance(dep, dict):
            errors.append(f"{at} must be a mapping of file: and pattern:")
            continue
        for field in sorted(set(dep) - set(MANIFEST_DEP_FIELDS)):
            errors.append(f"{at}/{field} is not a manifestDeps field "
                          f"({', '.join(MANIFEST_DEP_FIELDS)})")
        for field in MANIFEST_DEP_FIELDS:
            value = dep.get(field)
            if not isinstance(value, str) or not value:
                errors.append(f"{at}/{field} must be a non-empty string")
                continue
            if len(value) > SIGNAL_CAPS["manifestDeps"][1]:
                errors.append(f"{at}/{field} is longer than "
                              f"{SIGNAL_CAPS['manifestDeps'][1]} characters")
            try:
                re.compile(value)
            except re.error as exc:
                errors.append(f"{at}/{field} is not a valid regular expression: {exc}")
    return errors


def _signals(signals: dict, where: str) -> list[str]:
    errors = []
    for name in sorted(set(signals) - set(SIGNAL_CAPS)):
        errors.append(
            f"{_at(where, name)} is not a signal — Claude Code ignores it and the "
            f"plugin is never suggested through it "
            f"({', '.join(SIGNAL_CAPS)})")
    for name in SIGNAL_CAPS:
        if name not in signals:
            continue
        at = _at(where, name)
        entries = signals[name]
        if not isinstance(entries, list):
            errors.append(f"{at} must be a list")
            continue
        if not entries:
            errors.append(f"{at} is empty — drop it, or give it an entry")
            continue
        max_entries = SIGNAL_CAPS[name][0]
        if len(entries) > max_entries:
            errors.append(f"{at} has {len(entries)} entries, over the cap of {max_entries}")
        errors += (_manifest_deps(entries, at) if name == "manifestDeps"
                   else _string_entries(entries, name, at))
    return errors


def relevance_errors(relevance, where: str = "/relevance") -> list[str]:
    """Violations in one `relevance` block, as messages naming the field."""
    if not isinstance(relevance, dict):
        return [f"{where} must be a mapping of topic: and signals:, "
                f"but it is a {type(relevance).__name__}"]

    errors = [f"{_at(where, field)} is not a relevance field "
              f"({', '.join(RELEVANCE_FIELDS)})"
              for field in sorted(set(relevance) - set(RELEVANCE_FIELDS))]

    if "topic" in relevance:
        topic = relevance["topic"]
        if not isinstance(topic, str) or not topic:
            errors.append(f"{_at(where, 'topic')} must be a non-empty string")
        elif len(topic) > TOPIC_MAX:
            errors.append(f"{_at(where, 'topic')} is longer than {TOPIC_MAX} characters")

    signals = relevance.get("signals")
    if signals is None:
        errors.append(f"{_at(where, 'signals')} is required — a relevance block "
                      f"with no signal never suggests the plugin")
    elif not isinstance(signals, dict):
        errors.append(f"{_at(where, 'signals')} must be a mapping of signal names")
    elif not signals:
        errors.append(f"{_at(where, 'signals')} declares no signal")
    else:
        errors += _signals(signals, _at(where, "signals"))
    return errors


def dependency_errors(dependencies, plugin: str, allowed: set[str] | None = None,
                      where: str = "/dependencies") -> list[str]:
    """Violations in one plugin's hard `dependencies` list.

    `allowed` is the root marketplace's `allowCrossMarketplaceDependenciesOn`,
    which only the aggregator knows; pass None from a plugin repo to skip that
    cross-check rather than assert it from a file that can't see the answer.
    """
    if not isinstance(dependencies, list):
        return [f"{where} must be a list, but it is a "
                f"{type(dependencies).__name__}"]

    errors: list[str] = []
    names: list[str] = []
    for i, dep in enumerate(dependencies):
        at = f"{where}/{i}"
        if isinstance(dep, str):
            if not dep:
                errors.append(f"{at} must be a non-empty plugin name")
                continue
            names.append(dep)
            continue
        if not isinstance(dep, dict):
            errors.append(f"{at} must be a plugin name or a mapping with name:")
            continue
        for field in sorted(set(dep) - set(DEPENDENCY_FIELDS)):
            errors.append(f"{at}/{field} is not a dependency field "
                          f"({', '.join(DEPENDENCY_FIELDS)}) — Claude Code drops it, "
                          f"so the constraint it was meant to carry is not applied")
        name = dep.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{at}/name is required and must be a plugin name")
        else:
            names.append(name)
        if "version" in dep:
            version = dep["version"]
            if not isinstance(version, str) or not is_semver_range(version):
                errors.append(
                    f"{at}/version must be a semver range such as ~2.1.0, ^2.0, "
                    f">=1.4, or =2.1.0, but it is {version!r}")
        if "marketplace" in dep:
            market = dep["marketplace"]
            if not isinstance(market, str) or not market:
                errors.append(f"{at}/marketplace must be a marketplace name")
            elif allowed is not None and market not in allowed:
                errors.append(
                    f"{at}/marketplace names {market!r}, which the marketplace does "
                    f"not list in allowCrossMarketplaceDependenciesOn — installing "
                    f"{plugin} would fail with a cross-marketplace error")

    if plugin in names:
        errors.append(f"{where} lists {plugin} itself")
    for name in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"{where} lists {name} more than once")
    return errors


def raise_if(errors: list[str], source: str) -> None:
    """Report every violation at once, naming the file the author has to fix.

    One error per run would make a block with three mistakes three round trips,
    and this lands in a CI log or a plugin author's terminal, with shipyard's
    source nowhere in reach.
    """
    if not errors:
        return
    listed = "\n".join(f"  - {e}" for e in errors)
    raise SystemExit(f"shipyard: {source}\n{listed}")
