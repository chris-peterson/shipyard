"""shipyard command-line entry point.

Usage:
    shipyard <command> [--root PATH] [--check]

Commands project a target plugin repo's canonical sources into their generated
artifacts. ``--root`` selects the target repo (default: current directory).
``--check`` (where supported) verifies committed output matches, without
writing — the CI gate.
"""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shipyard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, *, check: bool = False, help: str = "") -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help)
        p.add_argument("--root", default=None, help="target plugin repo (default: cwd)")
        if check:
            p.add_argument("--check", action="store_true", help="verify sync without writing")
        return p

    add("gen-plugin-json", check=True, help="plugin.yml → .claude-plugin/plugin.json")
    add("gen-hooks-json", check=True, help="hooks/hooks.yml → hooks/hooks.json")
    add("gen-plugin-docs", check=True, help="plugin.yml suite: → docs/plugin-docs.json")
    add("gen-describe", check=True, help="source → plugin.yml suite.describe")
    add("build-docs", help="render skills/rules/… into docs/ (+ plugin-docs.json)")
    add("changelog", help="prepend a release section to CHANGELOG.md (VERSION/BODY env)")
    add("build", help="run every generator (plugin-json, describe, docs)")
    add("check", help="verify all generated artifacts are in sync (CI gate)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root
    check = getattr(args, "check", False)

    if args.command == "gen-plugin-json":
        from . import gen_plugin_json
        return gen_plugin_json.run(root, check=check)
    if args.command == "gen-hooks-json":
        from . import gen_hooks_json
        return gen_hooks_json.run(root, check=check)
    if args.command == "gen-plugin-docs":
        from . import gen_plugin_docs
        return gen_plugin_docs.run(root, check=check)
    if args.command == "gen-describe":
        from . import gen_describe
        return gen_describe.run(root, check=check)
    if args.command == "build-docs":
        from . import build_docs
        return build_docs.run(root)
    if args.command == "changelog":
        from . import changelog
        return changelog.run(root)
    if args.command == "build":
        # hooks.json first, so gen-describe reads the freshly-generated wiring
        from . import gen_hooks_json, gen_describe, gen_plugin_json, build_docs
        gen_hooks_json.run(root)
        gen_describe.run(root)
        gen_plugin_json.run(root)
        build_docs.run(root)
        return 0
    if args.command == "check":
        # only the committed generated artifacts — plugin.json, hooks.json, and
        # plugin.yml's describe. plugin-docs.json is a gitignored render target.
        from . import gen_hooks_json, gen_describe, gen_plugin_json
        gen_plugin_json.run(root, check=True)
        gen_hooks_json.run(root, check=True)
        gen_describe.run(root, check=True)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
