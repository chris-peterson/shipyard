"""shipyard command-line entry point.

Usage:
    shipyard <command> [--root PATH]

Commands project a target repo's canonical sources into their generated
artifacts. ``--root`` selects the target repo (default: current directory).

A target is one of two kinds, told apart by the manifest at its root:

* a **plugin** (``plugin.yml``) — its own descriptor, hooks, and docs.
* an **aggregator** (``plugins.yml``) — a marketplace or catalog site that
  presents a roster of plugins. Its per-plugin content is read from the rostered
  plugins' own ``plugin.yml`` in sibling checkouts, never restated locally.

``generate`` is the single projection verb for both, and it writes. CI is the
only thing that runs it: ``actions/project`` projects on every push and commits
the result to the branch, so a committed artifact matches its source at all times
rather than only after a release, and the diff a reviewer approves is the change
that lands.
"""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shipyard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, *, help: str = "") -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help)
        p.add_argument("--root", default=None, help="target plugin repo (default: cwd)")
        return p

    add("gen-plugin-json", help="plugin.yml → .claude-plugin/plugin.json")
    add("gen-hooks-json", help="hooks/hooks.yml → hooks/hooks.json")
    add("gen-plugin-docs", help="plugin.yml suite: → docs/plugin-docs.json")
    add("gen-describe", help="source → plugin.yml suite.describe")
    add("gen-cli-manifest",
        help="the declared CLI's --help → its committed grammar manifest")
    add("build-docs", help="render skills/rules/… into docs/ (+ plugin-docs.json); "
                           "plugin.yml `docs: resources:` names extra paths to publish")
    add("changelog", help="prepend a release section to CHANGELOG.md (VERSION/BODY env)")
    add("roster", help="plugins.yml → name/url pairs (no plugin checkouts needed)")
    add("gen-marketplace-json", help="plugins.yml + plugins → .claude-plugin/marketplace.json")
    add("gen-plugins-js", help="plugins' suite: blocks → docs/plugins.js")
    add("gen-deps-json", help="plugins' declared dependencies → docs/deps.json")
    add("generate", help="project source → artifacts")
    return parser


def _generate_aggregate(root: str | None) -> int:
    """The aggregator's projection. marketplace.json is the one committed
    artifact; the doc-site data is regenerated on every deploy."""
    from . import gen_deps_json, gen_marketplace_json, gen_plugins_js
    gen_marketplace_json.run(root)
    gen_plugins_js.run(root)
    gen_deps_json.run(root)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root

    if args.command == "gen-plugin-json":
        from . import gen_plugin_json
        return gen_plugin_json.run(root)
    if args.command == "gen-hooks-json":
        from . import gen_hooks_json
        return gen_hooks_json.run(root)
    if args.command == "gen-plugin-docs":
        from . import gen_plugin_docs
        return gen_plugin_docs.run(root)
    if args.command == "gen-describe":
        from . import gen_describe
        return gen_describe.run(root)
    if args.command == "gen-cli-manifest":
        from . import gen_cli_manifest
        return gen_cli_manifest.run(root)
    if args.command == "build-docs":
        from . import build_docs
        return build_docs.run(root)
    if args.command == "changelog":
        from . import changelog
        return changelog.run(root)
    if args.command == "roster":
        from . import roster
        return roster.run(root)
    if args.command == "gen-marketplace-json":
        from . import gen_marketplace_json
        return gen_marketplace_json.run(root)
    if args.command == "gen-plugins-js":
        from . import gen_plugins_js
        return gen_plugins_js.run(root)
    if args.command == "gen-deps-json":
        from . import gen_deps_json
        return gen_deps_json.run(root)
    if args.command == "generate":
        from ._aggregate import is_aggregate
        if is_aggregate(root):
            return _generate_aggregate(root)
        from . import (build_docs, gen_cli_manifest, gen_describe, gen_hooks_json,
                       gen_plugin_json)
        # hooks.json first, so gen-describe reads the freshly-generated wiring
        gen_hooks_json.run(root)
        gen_describe.run(root)
        gen_plugin_json.run(root)
        # before the docs, which render the manifest into the CLI reference page
        gen_cli_manifest.run(root)
        build_docs.run(root)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
