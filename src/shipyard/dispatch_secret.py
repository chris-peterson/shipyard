"""Fan the marketplace dispatch token out to the plugin repos.

    shipyard dispatch-secret [<name> ...] [--root AGGREGATOR]

A plugin's release dispatches a catalog rebuild into its marketplace, which the
release workflow's own GITHUB_TOKEN can't do across repos, so each plugin repo
holds a MARKETPLACE_DISPATCH_TOKEN secret: a PAT with Contents write on the
marketplace. This sets it on every plugin on the roster, or on the ones named,
and is the same command for a first setup, a new plugin, and a rotation.

The token comes from $MARKETPLACE_DISPATCH_TOKEN or a silent prompt, and reaches
`gh` on stdin or in its environment, never on a command line. A silent prompt
makes a truncated paste look like a good one, so the token is checked against
GitHub before anything is written: it must authenticate, and it must be able to
dispatch to the marketplace. The capability check sends a real dispatch with an
event type no workflow subscribes to, so it proves the permission without
starting a build.

The aggregator is found the way `shipyard onboarding` finds it.

Exit codes: 0 set · 1 the token failed a check or a write failed · 2 a tool error.
"""
from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from collections.abc import Callable

from ._aggregate import roster
from .onboarding import ToolError, find_aggregator

SECRET = "MARKETPLACE_DISPATCH_TOKEN"
PROBE_EVENT = "dispatch-token-probe"

KINDS = (("github_pat_", "fine-grained PAT"), ("ghp_", "classic PAT"),
         ("gho_", "GitHub-issued token"), ("ghu_", "GitHub-issued token"),
         ("ghs_", "GitHub-issued token"), ("ghr_", "GitHub-issued token"))


def _run(args: list[str], *, token: str | None = None, stdin: str | None = None
         ) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if token is not None:
        env["GH_TOKEN"] = token
    return subprocess.run(args, input=stdin, capture_output=True, text=True, env=env)


# Replaced in tests, so no call reaches GitHub.
run: Callable[..., subprocess.CompletedProcess] = _run
prompt: Callable[[str], str] = getpass.getpass


def kind(token: str) -> str:
    return next((label for prefix, label in KINDS if token.startswith(prefix)),
                "unrecognized prefix")


def marketplace_repo(root) -> str:
    """owner/name of the aggregator, from its origin remote."""
    proc = run(["git", "-C", str(root), "remote", "get-url", "origin"])
    if proc.returncode != 0:
        raise ToolError(f"{root} has no origin remote: {proc.stderr.strip()}")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", proc.stdout.strip())
    if not m:
        raise ToolError(f"origin of {root} is not a GitHub repo: {proc.stdout.strip()}")
    return m.group(1)


def read_token() -> str:
    token = os.environ.get(SECRET) or prompt(f"{SECRET} value: ")
    trimmed = token.strip()
    if trimmed != token:
        print("note: trimmed surrounding whitespace from the value")
    if not trimmed:
        raise ToolError("no token provided")
    return trimmed


def check(token: str, target: str) -> bool:
    print(f"read {len(token)} chars, {kind(token)}")
    who = run(["gh", "api", "user", "--jq", ".login"], token=token)
    if who.returncode != 0:
        print(f"the token does not authenticate: {who.stderr.strip()}", file=sys.stderr)
        print("generate a fresh PAT and re-run", file=sys.stderr)
        return False
    headers = run(["gh", "api", "user", "--include"], token=token).stdout
    expiry = re.search(r"^github-authentication-token-expiration:\s*(.+?)\s*$", headers,
                       re.I | re.M)
    print(f"authenticates as {who.stdout.strip()}"
          + (f", expires {expiry.group(1)}" if expiry else ""))
    probe = run(["gh", "api", f"repos/{target}/dispatches", "-f", f"event_type={PROBE_EVENT}"],
                token=token)
    if probe.returncode != 0:
        print(f"the token cannot dispatch to {target}: {probe.stderr.strip()}", file=sys.stderr)
        print(f"grant it Contents: Read and write on {target} (fine-grained), "
              "or the repo scope (classic)", file=sys.stderr)
        return False
    print(f"can repository_dispatch to {target}")
    return True


def main(names: list[str], root=None) -> int:
    try:
        aggregator = find_aggregator(root)
        target = marketplace_repo(aggregator)
        owner = target.split("/")[0]
        listed = [name for name, _ in roster(aggregator)]
        for name in names:
            if name not in listed:
                print(f"note: {name} is not on {aggregator.name}'s plugins.yml")
        token = read_token()
    except ToolError as exc:
        print(f"shipyard dispatch-secret: {exc}", file=sys.stderr)
        return 2
    if not check(token, target):
        return 1
    failed = 0
    for name in names or listed:
        print(f"setting {SECRET} on {owner}/{name}")
        proc = run(["gh", "secret", "set", SECRET, "--repo", f"{owner}/{name}"], stdin=token)
        if proc.returncode != 0:
            print(f"  failed: {proc.stderr.strip()}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0
