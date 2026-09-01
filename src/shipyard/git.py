"""The git the release driver needs, and nothing else.

Every call here is a read except `commit`, `tag`, and `push`, which the driver
reaches only after its preflight has passed and the operator has confirmed.

The tag reader takes `--match 'v[0-9]*.[0-9]*.[0-9]*'` rather than a bare
`describe`. A repo on this flow carries moving major aliases (`v1`, `v2`) beside
its immutable releases, and both sit on the same commits: a bare
`git describe --tags --abbrev=0` in shipyard's own checkout answers `v2`, which
would make the release read its changes from an empty range.
"""
from __future__ import annotations

import pathlib
import subprocess

# `%x1f` between fields and `%x1e` between records: a commit subject can contain
# anything a person can type, so the separators have to be bytes they can't.
_FIELD, _RECORD = "\x1f", "\x1e"

RELEASE_TAG_GLOB = "v[0-9]*.[0-9]*.[0-9]*"


class GitError(RuntimeError):
    """A git command that failed, carrying what it printed."""


def run(root: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ("git", "-C", str(root), *args),
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def ok(root: pathlib.Path, *args: str) -> bool:
    """Whether a git command succeeds, for the ones whose exit code is the answer."""
    try:
        run(root, *args)
    except GitError:
        return False
    return True


def branch(root: pathlib.Path) -> str:
    return run(root, "rev-parse", "--abbrev-ref", "HEAD")


def dirty_paths(root: pathlib.Path) -> list[str]:
    """Tracked files differing from HEAD, staged or not.

    `diff --name-only HEAD` rather than `status --porcelain`: it emits bare paths,
    where porcelain prefixes each with a two-column status that has to be sliced
    off — and `run` strips the output, so a leading blank column silently shifts
    that slice by one and takes the first character of the path with it.

    Untracked files are left out either way: a release rewrites tracked files
    only, so a scratch file in the checkout is not a reason to refuse one."""
    return run(root, "diff", "--name-only", "HEAD").splitlines()


def release_tags(root: pathlib.Path) -> list[tuple[str, str]]:
    """Every `vX.Y.Z` tag with the ISO instant of the commit it points at,
    oldest first.

    A release's instant comes from the tag rather than from the forge because a
    projection reads the checkout it was given. The two are the same CI run:
    `stage-release` commits the retitled section, tags that commit, and publishes
    from it, so the tag is where the version bump happened.
    """
    out = run(root, "for-each-ref", "--sort=creatordate",
              "--format=%(refname:strip=2)%09%(creatordate:iso-strict)",
              f"refs/tags/{RELEASE_TAG_GLOB}")
    pairs = []
    for line in out.splitlines():
        if "\t" in line:
            name, at = line.split("\t", 1)
            pairs.append((name, at.strip()))
    return pairs


def last_release_tag(root: pathlib.Path) -> str | None:
    """The newest `vX.Y.Z` tag reachable from HEAD, or None on a repo with none."""
    try:
        return run(root, "describe", "--tags", "--abbrev=0",
                   "--match", RELEASE_TAG_GLOB)
    except GitError:
        return None


def tag_exists(root: pathlib.Path, name: str) -> bool:
    return ok(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{name}")


def remote_branch_exists(root: pathlib.Path, remote: str, name: str) -> bool:
    return ok(root, "ls-remote", "--exit-code", "--heads", remote, name)


def fetch(root: pathlib.Path, remote: str) -> None:
    run(root, "fetch", "--quiet", remote, "--tags")


def ahead_behind(root: pathlib.Path, upstream: str) -> tuple[int, int]:
    """How many commits HEAD is ahead of and behind `upstream`."""
    out = run(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    behind, ahead = out.split()
    return int(ahead), int(behind)


class Change:
    """One commit in the range a release covers."""

    __slots__ = ("sha", "subject", "pr")

    def __init__(self, sha: str, subject: str, pr: str | None):
        self.sha, self.subject, self.pr = sha, subject, pr

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Change({self.sha}, {self.subject!r}, pr={self.pr})"


def _pr_number(subject: str, body: str) -> str | None:
    """The PR a commit came through, when it says so.

    Squash merges put `(#24)` in the subject; a merge commit says
    `Merge pull request #24`. A commit that mentions neither has no PR to link,
    and inventing one from proximity would produce a changelog line pointing at
    somebody else's change."""
    import re
    m = re.search(r"\(#(\d+)\)\s*$", subject)
    if m:
        return m.group(1)
    m = re.search(r"^Merge pull request #(\d+)", subject)
    if m:
        return m.group(1)
    m = re.search(r"^(?:Closes|Fixes|Refs):?\s+#(\d+)\s*$", body, re.M)
    return m.group(1) if m else None


def changes(root: pathlib.Path, since: str | None) -> list[Change]:
    """The commits a release would cover, newest first.

    `since` is the previous release tag, or None on a repo that has never
    released — in which case the range is the whole history rather than empty,
    because a first release's notes cover everything in it."""
    fmt = f"%H{_FIELD}%s{_FIELD}%b{_RECORD}"
    rev = f"{since}..HEAD" if since else "HEAD"
    out = run(root, "log", rev, "--no-merges", f"--format={fmt}")
    found = []
    for record in out.split(_RECORD):
        record = record.strip("\n")
        if not record.strip():
            continue
        sha, subject, body = (record.split(_FIELD) + ["", ""])[:3]
        found.append(Change(sha[:7], subject.strip(), _pr_number(subject, body)))
    return found


def commit(root: pathlib.Path, message: str, paths: list[str]) -> None:
    run(root, "add", "--", *paths)
    run(root, "commit", "--message", message)


def tag(root: pathlib.Path, name: str, *, force: bool = False) -> None:
    run(root, "tag", *(("--force",) if force else ()), name)


def push(root: pathlib.Path, remote: str, *refs: str, force: bool = False) -> None:
    """Push refs together or not at all.

    `--atomic` is the mechanism behind the whole ordering guarantee: the branch
    and the tag naming its head land in one remote transaction, so there is no
    window in which the tag exists and the commit it names does not."""
    run(root, "push", "--atomic", *(("--force",) if force else ()), remote, *refs)
