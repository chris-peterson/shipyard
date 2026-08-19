"""Derive the next version from a bump level.

The release takes a bump level rather than a literal version. Two reasons, both
about removing a way for the tag and the version to disagree: a level is what a
human can supply without looking anything up, and the next version is then
computed from what the repo already says it is rather than retyped.

Where "what the repo says it is" lives depends on the kind of repo — a plugin's
`plugin.yml`, shipyard's own `pyproject.toml` — so reading and writing it is the
caller's job. The arithmetic is here, and it is the same for both.
"""
from __future__ import annotations

import pathlib
import re

LEVELS = ("major", "minor", "patch")

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# `version = "1.2.3"` on its own line, under [project]. Matched rather than
# parsed so the bump rewrites one line and leaves the file's formatting and
# comments alone — the same reason gen-describe splices instead of re-emitting.
_PYPROJECT_VERSION = re.compile(r'^(version\s*=\s*")(\d+\.\d+\.\d+)(")$', re.M)


def parse(version: str) -> tuple[int, int, int]:
    m = _SEMVER.match(version.strip())
    if not m:
        raise SystemExit(
            f"shipyard: {version!r} is not a major.minor.patch version. The release "
            "derives the next one from it, so it has to be readable.")
    return tuple(int(p) for p in m.groups())  # type: ignore[return-value]


def next_version(current: str, level: str) -> str:
    """`current` bumped by `level`.

    A major bump zeroes minor and patch, a minor bump zeroes patch. Nothing here
    knows about pre-release or build metadata: the suite has never published one,
    and accepting a shape the rest of the flow can't tag would fail later and
    further from the input that caused it."""
    if level not in LEVELS:
        raise SystemExit(
            f"shipyard: {level!r} is not a bump level. Use one of: "
            + ", ".join(LEVELS))
    major, minor, patch = parse(current)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def read_pyproject(root: str | pathlib.Path | None = None) -> str:
    """shipyard's own recorded version.

    shipyard is not a plugin, so it has no `plugin.yml` to carry this; its
    `pyproject.toml` is the equivalent manifest at the repo root, and the release
    bumps it there for the same reason."""
    path = pathlib.Path(root or ".") / "pyproject.toml"
    m = _PYPROJECT_VERSION.search(path.read_text())
    if not m:
        raise SystemExit(f"shipyard: {path} has no `version = \"X.Y.Z\"` line.")
    return m.group(2)


def write_pyproject(new: str, root: str | pathlib.Path | None = None) -> None:
    path = pathlib.Path(root or ".") / "pyproject.toml"
    text, count = _PYPROJECT_VERSION.subn(rf"\g<1>{new}\g<3>", path.read_text(), count=1)
    if count != 1:
        raise SystemExit(f"shipyard: {path} has no `version = \"X.Y.Z\"` line to bump.")
    path.write_text(text)


# `version: 1.2.3` in plugin.yml. Same one-line rewrite as pyproject, and for the
# same reason: plugin.yml is hand-authored around this key.
_PLUGIN_VERSION = re.compile(r"^(version:[ \t]*)(\d+\.\d+\.\d+)[ \t]*$", re.M)


def read_plugin_yml(root: str | pathlib.Path | None = None) -> str:
    path = pathlib.Path(root or ".") / "plugin.yml"
    m = _PLUGIN_VERSION.search(path.read_text())
    if not m:
        raise SystemExit(
            f"shipyard: {path} has no `version: X.Y.Z` line. The release derives "
            "the next version from it.")
    return m.group(2)


def write_plugin_yml(new: str, root: str | pathlib.Path | None = None) -> None:
    path = pathlib.Path(root or ".") / "plugin.yml"
    text, count = _PLUGIN_VERSION.subn(rf"\g<1>{new}", path.read_text(), count=1)
    if count != 1:
        raise SystemExit(f"shipyard: {path} has no `version: X.Y.Z` line to bump.")
    path.write_text(text)
