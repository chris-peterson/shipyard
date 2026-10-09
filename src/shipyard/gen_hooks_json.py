"""Project hooks/hooks.yml → hooks/hooks.json.

hooks.yml is the source of record for a plugin's hooks — a flat, commentable
list where each entry carries the Claude event it fires on, an optional tool
matcher, the command it runs, and a one-line description. Claude Code reads the
generated hooks.json (the same source-of-record → generated-artifact split as
plugin.yml → plugin.json), and gen-describe reads the descriptions straight from
hooks.yml, so no `# DOCUMENTATION:` line in the hook scripts is needed.

An entry may also carry the command-hook fields in HOOK_FIELDS, which reach
hooks.json as written. Any other key is an error: projected, it would be a
field Claude Code ignores, and dropped, it would be a setting that silently
never applied.

    hooks:
      - event: SessionStart
        command: bash "${CLAUDE_PLUGIN_ROOT}/hooks/emit-rules.sh"
        description: Emits the plugin's ambient rules into the agent's context.
      - event: PreToolUse
        matcher: Bash
        command: python3 "${CLAUDE_PLUGIN_ROOT}/scripts/watchdog.py"
        timeout: 10
        onFailure: block
        description: Screens the command before it runs.

Entries are grouped into hooks.json by (event, matcher), preserving order, so
`command` is stored verbatim and the JSON round-trips byte-for-byte.
"""
from __future__ import annotations

import json
import pathlib

from . import _validate
from ._common import load_mapping, plugin_root

HOOKS_SHAPE = "a mapping with a `hooks:` list"

# `description` is shipyard's own, read by gen-describe and build-docs; `event`
# and `matcher` place the hook in hooks.json rather than ride on it.
ENTRY_FIELDS = ("event", "matcher", "command", "description")
REQUIRED = ("event", "command")

# The command-hook fields Claude Code reads, from
# https://code.claude.com/docs/en/hooks. Their values are left to
# `claude plugin validate`, which checks each one and warns on a bad value.
HOOK_FIELDS = ("args", "async", "asyncRewake", "if", "onFailure", "shell",
               "statusMessage", "timeout")


def hooks_yml_path(root: str | pathlib.Path | None = None) -> pathlib.Path:
    return plugin_root(root) / "hooks" / "hooks.yml"


def load_hooks(path: pathlib.Path) -> list:
    """The declared hook entries. The one reader of hooks.yml — build-docs and
    gen-describe come through here too, so a shape it rejects is rejected for
    every projection rather than by whichever one ran first."""
    entries = load_mapping(path, HOOKS_SHAPE).get("hooks")
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise SystemExit(
            f"shipyard: {path} `hooks:` must be a list of entries, but it is "
            f"a {type(entries).__name__}")
    errors: list[str] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SystemExit(
                f"shipyard: {path} has a hook entry that is a "
                f"{type(entry).__name__}, not a mapping: {entry!r}")
        at = f"/hooks/{i}"
        for field in sorted(set(entry) - set(ENTRY_FIELDS) - set(HOOK_FIELDS)):
            errors.append(f"{at}/{field} is not a hooks.yml field "
                          f"({', '.join(ENTRY_FIELDS + HOOK_FIELDS)})")
        for field in REQUIRED:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{at}/{field} is required and must be a "
                              f"non-empty string")
    _validate.raise_if(errors, f"{path} declares hooks shipyard cannot project:")
    return entries


def build(root: str | pathlib.Path | None = None) -> str:
    entries = load_hooks(hooks_yml_path(root))
    events: dict[str, list] = {}  # event -> [ [matcher, [hook, ...]], ... ]
    for e in entries:
        event, matcher = e["event"], e.get("matcher")
        hook = {"type": "command", "command": e["command"]}
        hook.update((k, v) for k, v in e.items() if k in HOOK_FIELDS)
        groups = events.setdefault(event, [])
        grp = next((g for g in groups if g[0] == matcher), None)
        if grp is None:
            grp = [matcher, []]
            groups.append(grp)
        grp[1].append(hook)

    out: dict[str, list] = {}
    for event, groups in events.items():
        arr = []
        for matcher, hooks in groups:
            group: dict = {}
            if matcher is not None:
                group["matcher"] = matcher
            group["hooks"] = hooks
            arr.append(group)
        out[event] = arr
    return json.dumps({"hooks": out}, indent=2) + "\n"


def run(root: str | pathlib.Path | None = None) -> int:
    # a plugin with no hooks.yml isn't on this model yet — nothing to do
    if not hooks_yml_path(root).exists():
        return 0
    generated = build(root)
    target = plugin_root(root) / "hooks" / "hooks.json"
    target.write_text(generated)
    return 0
