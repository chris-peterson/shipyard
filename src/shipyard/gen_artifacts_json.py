"""Project the aggregator's artifact log and its spokes' releases → docs/artifacts.json.

The growth view answers one question: what has the suite shipped, and when. Two
sources feed it, and both are read from the checkouts on disk.

The **artifact log** (`plugins.yml`'s `artifacts:`) is a change log of each
plugin's named skills, rules, hooks, commands, and agents. Replaying it gives a
total per plugin at any point, which the chart stacks per weekly bucket. Buckets
are regular weeks so the time axis is linear: equal spacing means equal elapsed
time, which a per-change-point axis would not give.

The **releases** are each spoke's `vX.Y.Z` tags paired with the `## <version>`
section of its CHANGELOG.md. That file is the release's source of record — the
same section `stage-release` retitles, commits, tags, and publishes — so reading
it here means the catalog and the release page cannot say different things, and
the projection needs no forge call to find out what shipped.

Dates stay instants. Which calendar day a release near midnight UTC lands on
depends on where it is read from, so the day is the browser's call, not this
projection's.

docs/artifacts.json is a render target, regenerated on every docs build.
"""
from __future__ import annotations

import csv
import json
import pathlib
from datetime import date, timedelta

from . import changelog, git
from ._aggregate import CATS, grouped, load_manifest, source_url, workspace
from ._common import plugin_root


def week_buckets(first: str) -> list[date]:
    """Monday-start week boundaries from the week of `first` through this week."""
    start = date.fromisoformat(first)
    start -= timedelta(days=start.weekday())
    buckets, cur = [], start
    while cur <= date.today():
        buckets.append(cur)
        cur += timedelta(days=7)
    return buckets


def log_rows(root: str | pathlib.Path | None = None) -> list[dict]:
    declared = load_manifest(root).get("artifacts")
    if not declared:
        raise SystemExit(
            "shipyard: plugins.yml declares no artifacts: log — the growth view "
            "is a projection of it, so there is nothing to build without one")
    path = plugin_root(root) / declared
    if not path.exists():
        raise SystemExit(f"shipyard: plugins.yml declares artifacts: {declared}, but {path} is missing")
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def build_series(rows: list[dict], plugins: list[str],
                 buckets: list[date]) -> dict[str, list[int | None]]:
    """Per plugin, a forward-filled total artifact count at each weekly bucket.

    Each total is the sum of that plugin's category counts at the latest change
    point on or before the bucket's week end, and None before its first change
    point — which is what keeps a plugin's band out of the weeks before it
    existed rather than drawing it as a zero.
    """
    series = {}
    for p in plugins:
        points = sorted((r for r in rows if r["plugin"] == p), key=lambda r: r["date"])
        totals, cur, i = [], None, 0
        for b in buckets:
            week_end = (b + timedelta(days=6)).isoformat()
            while i < len(points) and points[i]["date"] <= week_end:
                cur = sum(int(points[i].get(c) or 0) for c in CATS)
                i += 1
            totals.append(cur)
        series[p] = totals
    return series


def release_url(source: str, tag: str) -> str:
    """The forge page for one release, from the plugin's repository URL.

    Derived rather than fetched: the tag is what a release is published from, and
    `source:` already resolves where the plugin lives, so the link needs no forge
    call the rest of this projection has managed to do without.
    """
    return f"{source.removesuffix('.git')}/releases/tag/{tag}"


def spoke_releases(name: str, root: str | pathlib.Path | None = None) -> list[dict]:
    """One plugin's releases as ``{tag, published_at, url, summary}``, oldest first.

    A tag with no section in the spoke's CHANGELOG.md is reported as a release
    with no teaser rather than skipped or guessed at: the version shipped, and
    the listing says so, but nothing here invents notes for it.
    """
    spoke = workspace(root) / name
    source = source_url(load_manifest(root))(name)
    out = []
    for tag, at in git.release_tags(spoke):
        body = changelog.released_body(tag.lstrip("v"), spoke)
        out.append({"tag": tag, "published_at": at,
                    "url": release_url(source, tag),
                    "summary": changelog.teaser(body or "")})
    return out


def build_changelog(rows: list[dict],
                    releases: dict[str, list[dict]]) -> tuple[list[dict], dict[str, dict]]:
    """One entry per dated change point, newest first, plus the releases a
    retirement has claimed.

    A retired plugin's entry carries the last version it shipped, since that is
    the one anyone still has installed. That release is then reported on the
    retirement line alone, so it doesn't also open an entry of its own.
    """
    entries: dict[tuple[str, str], dict] = {}
    retired: dict[str, dict] = {}
    for r in rows:
        e = entries.setdefault((r["date"], r["plugin"]),
                               {"date": r["date"], "plugin": r["plugin"]})
        e["change"] = r["change"]
        if r.get("at"):
            e["at"] = r["at"]  # rows recorded before the column stay date-only
        if "-plugin:" in r["change"]:
            e["removed"] = True
            retired[r["plugin"]] = e

    claimed: dict[str, dict] = {}
    for name, entry in retired.items():
        last = max(releases.get(name) or [],
                   key=lambda r: r["published_at"], default=None)
        if last:
            claimed[name] = last
            entry["last_release"] = dict(last)

    return sorted(entries.values(), key=lambda r: (r["date"], r["plugin"]),
                  reverse=True), claimed


def build_releases(plugins: list[str], releases: dict[str, list[dict]],
                   claimed: dict[str, dict]) -> list[dict]:
    """Every release as a bare instant for the doc site to date locally, minus
    the ones a retirement already reported."""
    return [{"plugin": p, **rel}
            for p in plugins
            for rel in releases.get(p, [])
            if rel is not claimed.get(p)]


def build(root: str | pathlib.Path | None = None) -> dict:
    rows = log_rows(root)
    if not rows:
        raise SystemExit("shipyard: the artifacts log is empty — nothing to project")
    dates = sorted({r["date"] for r in rows})
    logged = {r["plugin"] for r in rows}

    # Catalog order, restricted to the plugins the log covers: a group's slot is
    # presentation, but a plugin with no logged history has no band to draw.
    plugins, colors = [], {}
    for name, key, shade in grouped(root):
        if name in logged:
            plugins.append(name)
            colors[name] = {"group": key, "shade": shade}

    buckets = week_buckets(dates[0])
    releases = {p: spoke_releases(p, root) for p in plugins}
    entries, claimed = build_changelog(rows, releases)

    return {
        "dates": [b.isoformat() for b in buckets],
        "plugins": plugins,
        "colors": colors,
        "series": build_series(rows, plugins, buckets),
        "changelog": entries,
        "releases": build_releases(plugins, releases, claimed),
    }


def run(root: str | pathlib.Path | None = None) -> int:
    target = plugin_root(root) / "docs" / "artifacts.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build(root), indent=2, ensure_ascii=False) + "\n")
    return 0
