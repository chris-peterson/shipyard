"""Derive plugin.yml's `suite: describe:` block from the plugin's own source.

Each artifact's source is its own source of record — so the one-line tooltip copy
the marketplace shows is *computed*, never hand-written:

  skill    -> first sentence of skills/<name>/SKILL.md `description:`
  command  -> first sentence of commands/<name>.md `description:`
  rule     -> first `# ` heading of rules/<name>.md
  hook      -> the event(s) it's wired to in hooks/hooks.json, plus the script's
              `# DOCUMENTATION:` line; hooks.json itself -> the full event→target wiring

The block is written into plugin.yml between generated markers, so the rest of
the (hand-authored) file is never reformatted. Downstream consumers — the
plugin's own docs (via plugin-docs.json) and the bridge.ai catalog — read the synced
plugin.yml, so neither reaches into source or carries its own copy.
"""
from __future__ import annotations

import json
import pathlib
import re

import yaml

from ._common import plugin_root
from .gen_hooks_json import load_hooks

BEGIN = "  # >>> shipyard:describe — generated from source by `shipyard gen-describe`; do not edit >>>"
END = "  # <<< shipyard:describe <<<"


# ---- derivation from source ------------------------------------------------

def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.search(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text).strip()


def _frontmatter_desc(md: pathlib.Path) -> str:
    parts = md.read_text().split("---")
    if len(parts) >= 3:
        fm = yaml.safe_load(parts[1]) or {}
        if isinstance(fm, dict) and fm.get("description"):
            return _first_sentence(str(fm["description"]))
    return ""


def _rule_heading(md: pathlib.Path) -> str:
    for line in md.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _target_label(cmd: str) -> str:
    m = re.search(r"hooks/([\w.-]+)\.(?:sh|py)", cmd)
    if m:
        return m.group(1)
    m = re.search(r"scripts/([\w.-]+)\"?\s+hook\b", cmd)
    if m:
        return f"{m.group(1)} CLI"
    # a helper/engine script the hook delegates to (e.g. a watch engine):
    # scripts/watchdog.py -> "watchdog"
    m = re.search(r"scripts/([\w.-]+)\.(?:py|sh)", cmd)
    if m:
        return m.group(1)
    return "?"


def _event_map(hooks_json: pathlib.Path) -> dict[str, list[str]]:
    data = json.loads(hooks_json.read_text())
    out: dict[str, list[str]] = {}
    for event, groups in (data.get("hooks") or {}).items():
        for group in groups:
            for h in group.get("hooks", []):
                tgt = _target_label(h.get("command", ""))
                out.setdefault(tgt, [])
                if event not in out[tgt]:
                    out[tgt].append(event)
    return out


def _doc_line(path: pathlib.Path) -> str:
    text = path.read_text()
    m = re.search(r"^#\s*DOCUMENTATION:\s*(.+)$", text, re.M)
    if m:
        return _first_sentence(m.group(1).strip())
    return ""


def _hooks_yml_desc(hooks_yml: pathlib.Path) -> dict[str, str]:
    """Each hook's description, keyed by the script stem / engine it delegates to
    (via _target_label), read from hooks.yml — the source of record."""
    entries = load_hooks(hooks_yml)
    out: dict[str, str] = {}
    for e in entries:
        if e.get("description"):
            out[_target_label(e.get("command", ""))] = _first_sentence(str(e["description"]))
    return out


def _hooks_wiring(hooks_json: pathlib.Path) -> str:
    """The event→target wiring, per event, annotating the tool matcher(s) each
    target responds to. Surfaces engine scripts (e.g. a watchdog) alongside the
    Claude event + matcher they fire on: `PreToolUse→watchdog (Bash, Write|Edit)`."""
    data = json.loads(hooks_json.read_text())
    parts = []
    for event, groups in (data.get("hooks") or {}).items():
        targets: dict[str, list[str]] = {}  # target -> matchers, order-preserving
        for group in groups:
            matcher = group.get("matcher")
            for h in group.get("hooks", []):
                t = _target_label(h.get("command", ""))
                targets.setdefault(t, [])
                if matcher and matcher not in targets[t]:
                    targets[t].append(matcher)
        rendered = [f"{t} ({', '.join(ms)})" if ms else t for t, ms in targets.items()]
        parts.append(f"{event}→{', '.join(rendered)}")
    return "Hook wiring: " + "; ".join(parts) + "."


def derive(root: str | pathlib.Path | None = None) -> dict:
    r = plugin_root(root)
    out: dict[str, dict[str, str]] = {}
    for d in sorted((r / "skills").glob("*/SKILL.md")):
        if desc := _frontmatter_desc(d):
            out.setdefault("skills", {})[d.parent.name] = desc
    for f in sorted((r / "rules").glob("*.md")):
        if h := _rule_heading(f):
            out.setdefault("rules", {})[f.stem] = h
    hooks_json = r / "hooks" / "hooks.json"
    hooks_yml = r / "hooks" / "hooks.yml"
    emap = _event_map(hooks_json) if hooks_json.exists() else {}
    # hooks.yml is the source of record for the descriptions when present; the
    # `# DOCUMENTATION:` line in the script is the pre-migration path.
    yml_desc = _hooks_yml_desc(hooks_yml) if hooks_yml.exists() else None
    for f in sorted((r / "hooks").glob("*")):
        if f.name == "hooks.json":
            out.setdefault("hooks", {})["hooks"] = _hooks_wiring(f)
        elif f.suffix in (".sh", ".py"):
            events = emap.get(f.stem, [])
            if yml_desc is not None:
                doc = yml_desc.get(f.stem, "")
                if not doc:
                    raise SystemExit(
                        f"shipyard gen-describe: hooks/hooks.yml has no description for {f.name} "
                        "(add a `description:` to its entry)."
                    )
            else:
                doc = _doc_line(f)
                if not doc:
                    raise SystemExit(
                        f"shipyard gen-describe: {f.relative_to(r)} has no `# DOCUMENTATION:` line "
                        "(add one below the shebang, or migrate the plugin to hooks.yml)."
                    )
            prefix = " / ".join(events) + " — " if events else ""
            out.setdefault("hooks", {})[f.stem] = prefix + doc
    for f in sorted((r / "commands").glob("*.md")):
        if desc := _frontmatter_desc(f):
            out.setdefault("commands", {})[f.stem] = desc
    return out


# ---- plugin.yml splice (marker-delimited, no reformat elsewhere) -----------

def render_block(describe: dict) -> str:
    body = yaml.safe_dump({"describe": describe}, sort_keys=False,
                          allow_unicode=True, width=10_000)
    indented = "\n".join("  " + line if line else line for line in body.splitlines())
    return f"{BEGIN}\n{indented}\n{END}"


def _suite_body(lines: list[str]) -> tuple[int, int]:
    """The half-open line range of `suite:`'s body — everything indented under it.

    `describe:` is a key *of* `suite:`, so the block has exactly one correct home
    and the file has to say where it is. Anything positional (append at the end,
    two-space indent) is only right while `suite:` happens to be the last
    top-level key, and lands the block under whichever key follows it otherwise:
    valid YAML, `suite.describe` absent, and nothing to see until a projection
    that reads it comes up empty."""
    for i, line in enumerate(lines):
        if not re.match(r"^suite:", line):
            continue
        if line.rstrip() != "suite:":
            # `suite: {sessions: []}` — a flow mapping has no block body, and
            # indenting a key under it is a parse error rather than a nesting.
            # Rewriting it as block style would reformat a hand-authored line,
            # which this module exists not to do.
            raise SystemExit(
                "shipyard gen-describe: plugin.yml writes `suite:` inline, so there "
                "is no block to add `describe:` to. Write `suite:` as a block "
                "mapping with its keys indented beneath it.")
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][:1] in " \t"):
            j += 1
        # Back off trailing blanks so the block lands against the last key
        # rather than after the gap before the next top-level one.
        while j > i + 1 and not lines[j - 1].strip():
            j -= 1
        return i + 1, j
    raise SystemExit(
        "shipyard gen-describe: plugin.yml has no `suite:` block. `describe:` is a "
        "key of `suite:`, so there is nowhere to write it — declare `suite:` first.")


def _without_existing(lines: list[str]) -> list[str]:
    """`lines` with any previously written describe removed, wherever it sits.

    Removing before inserting is what relocates a block an earlier run put in the
    wrong place, so a plugin carrying one is repaired by the next projection
    rather than keeping it forever."""
    begins = [i for i, l in enumerate(lines) if l.rstrip() == BEGIN.rstrip()]
    if begins:
        i = begins[0]
        j = next(k for k in range(i, len(lines)) if lines[k].rstrip() == END.rstrip())
        return lines[:i] + lines[j + 1:]
    # a plain (hand-authored) describe: and the lines indented under it
    plain = [i for i, l in enumerate(lines) if re.match(r"^  describe:\s*$", l)]
    if plain:
        i = plain[0]
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > 2):
            j += 1
        return lines[:i] + lines[j:]
    return lines


def _splice(text: str, block: str) -> str:
    lines = _without_existing(text.splitlines())
    start, end = _suite_body(lines)
    # Inside suite:, describe: sorts ahead of these two when the plugin has them.
    at = next((i for i, l in enumerate(lines[start:end], start)
               if l.rstrip() in ("  examples:", "  session:")), end)
    return "\n".join(lines[:at] + block.splitlines() + lines[at:]) + "\n"


def run(root: str | pathlib.Path | None = None) -> int:
    describe = derive(root)
    path = plugin_root(root) / "plugin.yml"
    path.write_text(_splice(path.read_text(), render_block(describe)))
    return 0
