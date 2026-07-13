"""shipyard command-line entry point.

Usage:
    shipyard <command> [--root PATH] [--dry-run]

Commands project a target plugin repo's canonical sources into their generated
artifacts. ``--root`` selects the target repo (default: current directory).

``generate`` is the single projection verb: it writes the artifacts, or with
``--dry-run`` validates the source is well-formed enough to project
and prints a diff of what the next write will apply, without touching the tree
and without failing on drift. The projection write happens at release (which
commits the result back), so between releases the committed artifacts are
expected to trail their source; preview surfaces that gap instead of gating on
it.
"""
from __future__ import annotations

import argparse
import os
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shipyard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, *, dry_run: bool = False,
            help: str = "") -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help)
        p.add_argument("--root", default=None, help="target plugin repo (default: cwd)")
        if dry_run:
            p.add_argument("--dry-run", action="store_true",
                           help="validate source and diff the pending projection; write nothing")
        return p

    add("gen-plugin-json", help="plugin.yml → .claude-plugin/plugin.json")
    add("gen-hooks-json", help="hooks/hooks.yml → hooks/hooks.json")
    add("gen-plugin-docs", help="plugin.yml suite: → docs/plugin-docs.json")
    add("gen-describe", help="source → plugin.yml suite.describe")
    add("build-docs", help="render skills/rules/… into docs/ (+ plugin-docs.json)")
    add("changelog", help="prepend a release section to CHANGELOG.md (VERSION/BODY env)")
    add("generate", dry_run=True,
        help="project source → artifacts (write); --dry-run to validate + diff only")
    return parser


def _emit_preview(diffs: list[str]) -> None:
    """Print pending-projection diffs and, in CI, append them to the job summary.
    Never sets a failure code — invalid source has already raised by this point."""
    body = (
        "### shipyard: pending projection\n\n"
        "The next `generate` (at release) will apply these changes to the "
        "committed artifacts:\n\n```diff\n" + "\n".join(diffs) + "\n```\n"
        if diffs else
        "### shipyard: pending projection\n\n"
        "✅ Committed artifacts already match their source — nothing to project.\n"
    )
    print("\n".join(diffs) if diffs
          else "shipyard: committed artifacts already match their source.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(body)


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
    if args.command == "build-docs":
        from . import build_docs
        return build_docs.run(root)
    if args.command == "changelog":
        from . import changelog
        return changelog.run(root)
    if args.command == "generate":
        from . import gen_hooks_json, gen_describe, gen_plugin_json, build_docs
        if getattr(args, "dry_run", False):
            # Dry-run the three committed artifacts. Each preview() calls its
            # build()/derive() first, so malformed/missing source still fails
            # loudly here — that's the only red condition. Diffs are derived from
            # the committed tree (nothing is written), so describe's wiring
            # reflects the committed hooks.json, not a freshly-generated one.
            diffs = [d for d in (
                gen_plugin_json.preview(root),
                gen_hooks_json.preview(root),
                gen_describe.preview(root),
            ) if d]
            _emit_preview(diffs)
            return 0
        # write: hooks.json first, so gen-describe reads the freshly-generated wiring
        gen_hooks_json.run(root)
        gen_describe.run(root)
        gen_plugin_json.run(root)
        build_docs.run(root)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
