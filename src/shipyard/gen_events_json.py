"""Project the rostered plugins' declared events → docs/events.json.

Both halves are *declared* in each plugin.yml, and deliberately asymmetric. A
producer declares the event in full under `events.publishes`, because it emits
the fields; a consumer declares only the key it depends on, under
`events.subscribes`, because N consumers restating one schema is N copies to
drift.

The catalog is what pairs them. Nothing at runtime reads it: the plugins find
each other by matching a line on stdout, and a subscriber that declared nothing
still works. What the catalog answers is the question no single repo can — which
keys have both ends, and which have only one.

That second answer is the point. A subscriber that never matches looks exactly
like an event that never fired, so an orphan on either side is the failure this
data makes visible:

- `subscribed_only` is always a defect — a typo, or a key whose publisher was
  renamed out from under it.
- `published_only` is usually a rollout in progress. The two ends ship from
  separate repos, so one lands first; it is a finding only when it stays that
  way.

docs/events.json is a render target — regenerated on every docs build, not
committed.
"""
from __future__ import annotations

import json
import pathlib

from ._aggregate import load_spokes
from ._common import plugin_root

# The suite's interop namespace. A producer declares its key bare and this
# supplies the rest, so a plugin cannot typo its own prefix.
NAMESPACE = "codes.bridgeai"


def qualify(plugin: str, key: str) -> str:
    return f"{NAMESPACE}.{plugin}/{key}"


def _events(spec: dict, half: str) -> list[dict]:
    return list((spec.get("events") or {}).get(half) or [])


def build(root: str | pathlib.Path | None = None) -> str:
    spokes = load_spokes(root)

    catalog: dict[str, dict] = {}
    for name, spec in spokes.items():
        for event in _events(spec, "publishes"):
            key = qualify(name, str(event.get("key", "")))
            catalog[key] = {
                "key": key,
                "publisher": name,
                "when": " ".join(str(event.get("when") or "").split()),
                "emitted_by": event.get("emitted_by", ""),
                "fields": _fields(event.get("fields")),
                "subscribers": [],
            }

    # A subscriber names someone else's key, fully qualified, so it lands on the
    # publisher's entry without the two repos agreeing on anything but the string.
    orphans: list[dict] = []
    for name, spec in spokes.items():
        for sub in _events(spec, "subscribes"):
            key = str(sub.get("key", ""))
            entry = {
                "subscriber": name,
                "handled_by": sub.get("handled_by", ""),
                "reason": " ".join(str(sub.get("reason") or "").split()),
            }
            if key in catalog:
                catalog[key]["subscribers"].append(entry)
            else:
                orphans.append({**entry, "key": key})

    for event in catalog.values():
        event["subscribers"].sort(key=lambda s: s["subscriber"])

    return json.dumps({
        "events": sorted(catalog.values(), key=lambda e: e["key"]),
        "subscribed_only": sorted(orphans, key=lambda s: (s["key"], s["subscriber"])),
        "published_only": sorted(k for k, e in catalog.items() if not e["subscribers"]),
    }, indent=2, ensure_ascii=False) + "\n"


def _fields(declared: object) -> list[dict]:
    """Each declared field, normalized.

    A plain string is shorthand for a required string field, which is what most
    of them are. The expanded form carries `describe`, `type`, and `optional` for
    a field a consumer must not rely on — a publisher that reads a value back
    from somewhere else can hand over an empty one."""
    out = []
    for name, spec in (declared or {}).items():
        if isinstance(spec, dict):
            out.append({
                "name": str(name),
                "type": spec.get("type", "string"),
                "optional": bool(spec.get("optional", False)),
                "describe": " ".join(str(spec.get("describe") or "").split()),
            })
        else:
            out.append({
                "name": str(name),
                "type": "string",
                "optional": False,
                "describe": " ".join(str(spec).split()),
            })
    return out


def run(root: str | pathlib.Path | None = None) -> int:
    target = plugin_root(root) / "docs" / "events.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build(root))
    return 0
