"""Cut a release: derive the version, retitle the notes, bump the manifest.

One verb, because the order matters and YAML is a poor place to keep an ordering
honest. The release run calls this once and then does the two things only it can:
tag the commit this produced, and publish the notes it printed.

    shipyard release --bump minor --notes-file notes.md
    version=1.3.0

What it deliberately does *not* do is commit, tag, or publish. Those are the
caller's, so this stays a pure function of the checkout: it can be run locally to
see exactly what a release would write, and discarded, the same way `generate`
can.

The sequence is the fix for the failure this replaces. The version used to come
from a tag a human cut *before* CI ran, so the bump commit always landed after the
tag that named it, and `plugin.json` at the tag reported the previous version.
Deriving the version here means the tag is cut from a commit that already carries
it.
"""
from __future__ import annotations

import pathlib
import sys

from . import changelog, version
from ._common import plugin_root


def _manifest(root: pathlib.Path) -> tuple[str, callable, callable]:
    """Which file carries this repo's version, and how to read and write it.

    A plugin's is `plugin.yml`. shipyard has no plugin.yml — it is not a plugin —
    so its own `pyproject.toml` is the equivalent manifest at the root. Anything
    else has no version to bump and says so rather than guessing at one."""
    if (root / "plugin.yml").exists():
        return "plugin.yml", version.read_plugin_yml, version.write_plugin_yml
    if (root / "pyproject.toml").exists():
        return "pyproject.toml", version.read_pyproject, version.write_pyproject
    raise SystemExit(
        f"shipyard: {root} carries neither plugin.yml nor pyproject.toml, so there "
        "is no version for a release to bump.")


def run(root: str | pathlib.Path | None = None, *, bump: str,
        notes_file: str | None = None) -> int:
    r = plugin_root(root)

    # Before the bump: an empty or absent `## Unreleased` fails the release, and
    # failing it with the manifest already rewritten would leave the repo
    # claiming a version that was never tagged.
    changelog.staged(r)

    name, read, write = _manifest(r)
    current = read(r)
    nxt = version.next_version(current, bump)

    notes = changelog.retitle(nxt, r)
    write(nxt, r)

    if notes_file:
        pathlib.Path(notes_file).write_text(notes.rstrip() + "\n")

    sys.stdout.write(f"version={nxt}\n")
    sys.stderr.write(
        f"shipyard release: {current} -> {nxt}, from {name}; "
        f"CHANGELOG.md section retitled.\n")
    return 0
