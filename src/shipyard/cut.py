"""Cut a release from the checkout you are standing in.

One verb. It reads what landed since the last release, drafts the notes into
`CHANGELOG.md` for you to shape, infers the bump from what you wrote, and then —
behind a single confirmation — commits, tags that commit, pushes both in one
transaction, and publishes the release from the section it committed.

Which of those two halves runs is decided by the file, not by a flag: an absent
or empty `## Unreleased` means there are no notes yet, so it drafts and stops. A
section with notes in it means the release is ready, so it ships. Re-running is
how you get from the first to the second, and re-running after a failure resumes
from wherever the file now is.

**Why local.** The three things a release has to line up — a body on the GitHub
release, a tag whose commit already carries the version, and a compare link that
includes the changelog — are all satisfiable by CI, and were. What CI could not
do was tell you *before* you committed to it: which version you were about to
publish, what body would be attached, or that your `## Unreleased` section was
empty. Every one of those was a red run you had to open and read. They are all
computable in a second from the checkout, so they happen here, before anything is
written.

**The one carve-out.** This makes the release commit a local write, where every
other generated artifact in the suite is written by CI. It is narrow on purpose:
`.claude-plugin/plugin.json` is the only committed artifact whose content a
release changes, its version is a one-key projection of `plugin.yml`, and
projecting it needs pyyaml and nothing from the plugin's own toolchain. The
preflight holds that line — it refuses to release a checkout whose `plugin.json`
does not already match its source, because that is a tree the projection job
still owes a commit to, and a release from it would land that commit *after* the
tag.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

from . import changelog, git, version
from ._common import plugin_root

RELEASE_COMMIT = "Release v{version}"


class Refused(SystemExit):
    """A preflight or a confirmation that stopped the release.

    Distinct from a git or gh failure only in that nothing has been written yet:
    everything raising this runs before the first write."""

    def __init__(self, message: str):
        super().__init__(f"shipyard: {message}")


# ---- what carries the version ---------------------------------------------

def _manifest(root: pathlib.Path):
    """Which file records this repo's version, how to read and write it, and
    whether releasing it also moves a `vX` alias.

    A plugin's version lives in `plugin.yml`, and consumers install it by
    version, so nothing follows its major. shipyard has no plugin.yml — it is not
    a plugin — so `pyproject.toml` is its equivalent manifest, and its consumers
    pin `uses: …@v2`, which has to keep resolving to the newest release on that
    line. The alias is a property of being depended on by ref, which is why it
    tracks the manifest kind rather than a flag someone has to remember."""
    if (root / "plugin.yml").exists():
        return "plugin.yml", version.read_plugin_yml, version.write_plugin_yml, False
    if (root / "pyproject.toml").exists():
        return "pyproject.toml", version.read_pyproject, version.write_pyproject, True
    raise Refused(
        f"{root} carries neither plugin.yml nor pyproject.toml, so there is no "
        "version for a release to bump.")


def _stale_projections(root: pathlib.Path) -> list[str]:
    """Committed artifacts that disagree with their source.

    Checked, not rewritten. A release that regenerated these would sweep an
    unreviewed change into the tagged commit, and a disagreement means the
    projection job still owes this branch a commit — so the answer is to go get
    that commit, not to project locally.

    Every check here reads YAML and writes JSON, needing pyyaml and nothing from
    the plugin's own toolchain. **The CLI manifest is deliberately not among
    them**, and that exclusion is the point rather than an omission: verifying it
    means running the plugin's CLI, which needs its build. The step this replaces
    ran the full `generate` on a checkout with no build ahead of it, so for a
    plugin whose committed entry point imports its dependencies at runtime, the
    CLI exited non-zero and killed the release before it committed the version
    bump. A release cannot depend on being able to build the thing it releases."""
    if not (root / "plugin.yml").exists():
        return []
    from . import gen_hooks_json, gen_plugin_json

    checks = [(root / ".claude-plugin" / "plugin.json", gen_plugin_json.build)]
    # A plugin with no hooks.yml isn't on that model, and gen_hooks_json writes
    # nothing for it, so there is nothing to disagree with.
    if (root / "hooks" / "hooks.yml").exists():
        checks.append((root / "hooks" / "hooks.json", gen_hooks_json.build))

    stale = []
    for target, build in checks:
        if not target.exists() or target.read_text() != build(root):
            stale.append(str(target.relative_to(root)))
    return stale


# ---- preflight -------------------------------------------------------------

class Plan:
    """Everything the release needs, resolved before anything is written."""

    def __init__(self, root, manifest, read, write, alias, current, last_tag, branch):
        self.root, self.manifest = root, manifest
        self.read, self.write, self.alias = read, write, alias
        self.current, self.last_tag, self.branch = current, last_tag, branch


def _gh(*args: str) -> str:
    proc = subprocess.run(("gh", *args), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"shipyard: gh {' '.join(args)} failed: "
            f"{(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def _preflight(root: pathlib.Path, *, remote: str, branch: str) -> Plan:
    try:
        on = git.branch(root)
    except git.GitError as exc:
        raise Refused(f"{root} is not a git checkout ({exc}).")

    if on != branch:
        raise Refused(
            f"on branch {on!r}, and a release is cut from {branch!r}. "
            f"`git switch {branch}` first.")
    # CHANGELOG.md is the exception, and the flow depends on it being one: the
    # draft half writes the worksheet and leaves it uncommitted, you rewrite it
    # into notes, and the ship half puts it in the release commit. Refusing a
    # dirty changelog would deadlock the two halves against each other. It also
    # means the notes and the version bump are one commit, which is what puts
    # them both inside the compare link between the two tags.
    dirty = [p for p in git.dirty_paths(root) if p != "CHANGELOG.md"]
    if dirty:
        raise Refused(
            "uncommitted changes to " + ", ".join(sorted(dirty)) + ". A release "
            "commits the notes and the version bump and nothing else, so it will "
            "not run over a tree it would have to guess about.")

    try:
        git.fetch(root, remote)
    except git.GitError as exc:
        raise Refused(f"cannot reach {remote} ({exc}).")

    ahead, behind = git.ahead_behind(root, f"{remote}/{branch}")
    if behind:
        raise Refused(
            f"{behind} commit(s) behind {remote}/{branch}. Releasing would tag a "
            f"commit that is not the head of {branch}. Pull first.")
    if ahead:
        raise Refused(
            f"{ahead} unpushed commit(s) on {branch}. A release publishes what is "
            f"already on {remote}/{branch} — push them, let CI project them, then "
            "release.")

    if not (root / "CHANGELOG.md").exists():
        raise Refused(
            f"no CHANGELOG.md at {root}. It is the source the release notes are "
            "read from, so there is nothing to release without it.")

    stale = _stale_projections(root)
    if stale:
        raise Refused(
            ", ".join(stale) + " does not match its source. That is a commit the "
            "projection job still owes this branch, and a release from here would "
            "land it after the tag. Push, let CI project, then release.")

    name, read, write, alias = _manifest(root)
    current = read(root)
    _gh("auth", "status")
    return Plan(root, name, read, write, alias, current,
                git.last_release_tag(root), branch)


# ---- the two halves --------------------------------------------------------

def _draft(plan: Plan, changes, *, force: bool) -> int:
    """Write the worksheet and stop.

    Stopping is the point rather than a limitation of the terminal. What turns
    commit subjects into release notes is a rewrite for a different reader, and
    whoever does it — a person in an editor, an agent with its own tools — needs
    the file to exist and the command to be out of the way while they work."""
    if not changes:
        raise Refused(
            f"nothing has landed since {plan.last_tag}, so there is nothing to "
            "release.")
    changelog.write_staged(changelog.draft(changes, plan.last_tag), plan.root,
                           force=force)
    span = f"since {plan.last_tag}" if plan.last_tag else "in the whole history"
    print(f"\n{len(changes)} commit(s) {span}, drafted into CHANGELOG.md's "
          "`## Unreleased`:\n")
    for c in changes:
        print(f"  {c.sha}  {c.subject}")
    print("\nSort those lines into the sections that apply and rewrite them for "
          "someone using this.\nThen run `shipyard release` again to publish.")
    return 0


def _rule(label: str) -> str:
    return f"{label} " + "─" * max(0, 66 - len(label))


def _preview(plan: Plan, nxt: str, level: str, because: str, body: str,
             tag: str) -> None:
    print()
    print(f"  {plan.current} → {nxt}   ({level}, from {because})")
    print(f"  recorded in {plan.manifest}"
          + (", projected into .claude-plugin/plugin.json"
             if plan.manifest == "plugin.yml" else ""))
    print()
    print(_rule("release body"))
    print(body)
    print("─" * 67)
    print()
    print(f"  commit   {RELEASE_COMMIT.format(version=nxt)}")
    print(f"  tag      {tag}  (on that commit)")
    if plan.alias:
        print(f"  alias    v{nxt.split('.')[0]}  moved to that commit")
    print(f"  push     {plan.branch} and {tag} together, atomically")
    print(f"  publish  {tag}, with the body above")
    print()


def _confirm(level: str, yes: bool) -> str:
    """The confirmation, which doubles as the bump override.

    The inferred level is the one thing here a reader might disagree with — a
    breaking change filed under `### Changed` reads as a patch, and nothing in
    the prose distinguishes it from a rewording. Taking the correction at the same
    keystroke as the approval means noticing it costs nothing to act on."""
    if yes:
        return level
    try:
        answer = input(f"release this as {level}? [y/N/major/minor/patch] ").strip()
    except EOFError:
        raise Refused(
            "no terminal to confirm on. Re-run with --yes once the preview above "
            "is what you want.")
    if answer.lower() in version.LEVELS:
        return answer.lower()
    if answer.lower() not in ("y", "yes"):
        raise Refused("stopped. Nothing was written.")
    return level


def _ship(plan: Plan, *, bump: str | None, yes: bool, remote: str) -> int:
    body = changelog.staged(plan.root)
    level, heading = version.infer_level(changelog.subsections(body))
    # Formatted here rather than in the preview: an inferred level is explained
    # by a heading in the notes, an override by the flag that supplied it, and
    # only the first of those is a heading to render as one.
    because = f"`### {heading}`"
    if bump:
        level, because = bump, "--bump"
    nxt = version.next_version(plan.current, level)
    tag = f"v{nxt}"

    if git.tag_exists(plan.root, tag):
        raise Refused(
            f"{tag} already exists. {nxt} has been released; write this release's "
            "notes under `## Unreleased` and cut the next one.")
    major = f"v{nxt.split('.')[0]}"
    if plan.alias and git.remote_branch_exists(plan.root, remote, major):
        raise Refused(
            f"a branch named {major} exists on {remote}, and this release would "
            f"also move a tag of that name. Which one a consumer's `uses: …@{major}` "
            "resolves to is not something to leave to chance — delete the branch "
            "first, then release.")

    _preview(plan, nxt, level, because, body, tag)
    chosen = _confirm(level, yes)
    if chosen != level:
        # The override changes the version, so the preview the operator approved
        # no longer describes what would happen. Re-run rather than ship a plan
        # nobody saw.
        print(f"\nRe-run with --bump {chosen} to see that plan and confirm it.")
        return 1

    body = changelog.retitle(nxt, plan.root)
    plan.write(nxt, plan.root)
    touched = ["CHANGELOG.md", plan.manifest]
    if plan.manifest == "plugin.yml":
        from . import gen_plugin_json
        gen_plugin_json.run(plan.root)
        touched.append(".claude-plugin/plugin.json")

    git.commit(plan.root, RELEASE_COMMIT.format(version=nxt), touched)
    git.tag(plan.root, tag)
    git.push(plan.root, remote, plan.branch, tag)
    print(f"pushed {plan.branch} and {tag}")

    if plan.alias:
        git.tag(plan.root, major, force=True)
        git.push(plan.root, remote, major, force=True)
        print(f"moved {major} onto {tag}")

    with tempfile.NamedTemporaryFile(
            "w", suffix=".md", prefix="shipyard-notes.", delete=False) as fh:
        fh.write(body.rstrip() + "\n")
        notes = fh.name
    url = _gh("release", "create", tag, "--title", tag, "--notes-file", notes)
    pathlib.Path(notes).unlink(missing_ok=True)
    print(f"published {url}")
    return 0


def run(root: str | pathlib.Path | None = None, *, bump: str | None = None,
        draft_only: bool = False, yes: bool = False, remote: str = "origin",
        branch: str = "main") -> int:
    r = plugin_root(root)
    plan = _preflight(r, remote=remote, branch=branch)

    # An empty or absent section means the notes don't exist yet, so draft them.
    # Anything else goes to the ship half — including a worksheet, which
    # `changelog.staged` refuses by name. Routing it here instead would re-draft
    # over notes someone is part-way through sorting.
    if draft_only or not changelog.staged_body(r):
        return _draft(plan, git.changes(r, plan.last_tag), force=draft_only)
    return _ship(plan, bump=bump, yes=yes, remote=remote)
