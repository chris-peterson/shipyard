"""Report what a plugin still needs before an aggregator can ship it.

    shipyard onboarding <name> [<name> ...] [--root AGGREGATOR]

Reads the plugin's sibling checkout, the aggregator (its ``plugins.yml`` and
README), the hub page the aggregator names under ``hub:``, and the plugin's
GitHub repo through ``gh``. Prints one row per check, with the fix for each gap.
Writes nothing.

The aggregator is ``--root``, else the current directory when it holds
``plugins.yml``, else the one sibling of the current directory that does. That
last step is what lets it run from inside a plugin checkout: the plugins sit
beside their aggregator, the way the aggregator's own sync step lays them out.

Exit codes: 0 every check passes, 1 at least one gap, 2 a tool or auth error.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from collections.abc import Callable

import yaml

from ._aggregate import MANIFEST, groups, load_manifest, workspace
from ._common import load_mapping

SECRET = "MARKETPLACE_DISPATCH_TOKEN"

Check = tuple[str, bool, str]


class ToolError(Exception):
    pass


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


# Replaced in tests, so the GitHub half runs without a network.
gh: Callable[..., subprocess.CompletedProcess] = _gh


def _ok(*args: str) -> str:
    proc = gh(*args)
    if proc.returncode != 0:
        raise ToolError(f"gh {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def _pages(repo: str) -> dict | None:
    proc = gh("api", f"repos/{repo}/pages")
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    if "HTTP 404" in proc.stderr:
        return None
    raise ToolError(f"gh api repos/{repo}/pages: {proc.stderr.strip()}")


def find_aggregator(root: str | pathlib.Path | None,
                    cwd: pathlib.Path | None = None) -> pathlib.Path:
    if root is not None:
        return pathlib.Path(root).resolve()
    here = (cwd or pathlib.Path.cwd()).resolve()
    if (here / MANIFEST).exists():
        return here
    siblings = sorted(p for p in here.parent.iterdir()
                      if p.is_dir() and (p / MANIFEST).exists())
    if len(siblings) == 1:
        return siblings[0]
    if not siblings:
        raise ToolError(
            f"no {MANIFEST} in {here} or beside it; pass --root <aggregator checkout>")
    raise ToolError(
        f"more than one aggregator beside {here} ({', '.join(p.name for p in siblings)}); "
        "pass --root to pick one")


def _hub_names(path: pathlib.Path) -> set[str]:
    names: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            if isinstance(node, dict):
                if "name" in node:
                    names.add(node["name"])
                walk(node.get("children"))

    walk(yaml.safe_load(path.read_text()))
    return names


def checks(name: str, root: pathlib.Path) -> list[Check]:
    manifest = load_manifest(root)
    owner = manifest.get("owner") or ""
    repo = f"{owner}/{name}"
    keys = [g["key"] for g in groups(root)]
    homepage = f"https://{owner}.github.io/{name}/#/"

    descriptor = workspace(root) / name / "plugin.yml"
    if not descriptor.exists():
        return [("plugin.yml", False,
                 f"no {descriptor}; clone {repo} beside {root.name}")]
    spec = load_mapping(descriptor, "a mapping of the plugin's fields")
    group = (spec.get("suite") or {}).get("group")
    listing = spec.get("marketplace") or {}

    meta = json.loads(_ok("repo", "view", repo, "--json", "visibility,homepageUrl"))
    pages = _pages(repo)
    secrets = _ok("secret", "list", "--repo", repo, "--json", "name",
                  "--jq", ".[].name").split()
    tags = _ok("api", f"repos/{repo}/tags", "--jq", ".[].name").split()

    readme = root / "README.md"
    rows: list[Check] = [
        ("suite.group", group in keys,
         f"plugin.yml `suite: group:` is {group!r}; set one of {keys}"),
        ("marketplace block", bool(listing.get("category") and listing.get("homepage")),
         f"add to plugin.yml: `marketplace:` with `category:` and `homepage: {homepage}`"),
        ("public repo", meta["visibility"] == "PUBLIC",
         f"gh repo edit {repo} --visibility public --accept-visibility-change-consequences"),
        ("repo homepage", bool(meta["homepageUrl"]),
         f"gh repo edit {repo} --homepage https://{owner}.github.io/{name}/"),
        ("Pages from Actions", bool(pages) and pages.get("build_type") == "workflow",
         f"gh api -X POST repos/{repo}/pages -f build_type=workflow "
         "(before the first push, or that push's docs deploy fails)"),
        (f"{SECRET} secret", SECRET in secrets,
         f"run `shipyard dispatch-secret {name}` in your own terminal; it prompts "
         "for the PAT, so the value never goes through a session"),
        (f"on {MANIFEST}", name in (manifest.get("plugins") or []),
         f"add `- {name}` to {MANIFEST} `plugins:` at its catalog position"),
        ("README section", readme.exists() and f"### [{name}](" in readme.read_text(),
         f"add a `### [{name}]({homepage})` section to {readme}"),
    ]
    hub = manifest.get("hub")
    if hub:
        hub_path = (root / hub).resolve()
        rows.append(("hub entry", hub_path.exists() and name in _hub_names(hub_path),
                     f"add a `- name: {name}` entry to {hub_path}"))
    rows.append(("released", any(t.startswith("v") for t in tags),
                 f"write CHANGELOG.md's `## Unreleased`, then run {repo}'s Release workflow"))
    return rows


def run(names: list[str], root: str | pathlib.Path | None = None) -> int:
    gaps = 0
    try:
        aggregator = find_aggregator(root)
        for name in names:
            print(name)
            for label, ok, fix in checks(name, aggregator):
                print(f"  {'ok ' if ok else 'GAP'}  {label}")
                if not ok:
                    gaps += 1
                    print(f"       fix: {fix}")
    except ToolError as exc:
        print(f"shipyard onboarding: {exc}", file=sys.stderr)
        return 2
    print(f"\n{gaps} gap(s)" if gaps else "\nready")
    return 1 if gaps else 0
