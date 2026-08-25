"""The local release driver: its preflight, its two halves, and its ordering.

The tests that matter most here are the refusals. Every one of them stands where a
red CI run used to be, and each guards something a tag makes permanent — a version
published twice, a worksheet published as notes, a tag on a commit that is not the
head of the branch. The happy path is checked for the one property the whole
design exists to produce: the tag names a commit that already carries the version
and the changelog section, and the published body is that section byte for byte.
"""
import pathlib
import subprocess

import pytest

from shipyard import changelog, cut, git

# Captured before the autouse stub below replaces it, so the one test that
# exercises the real subprocess call can still reach it.
_real_gh = cut._gh

PLUGIN_YML = """\
name: widget
version: 1.2.0
description: A widget
author: Someone
repository: https://github.com/someone/widget
"""

CHANGELOG = """\
# Changelog

Preamble that the release has no business touching.

## 1.2.0

### Added

- The previous release's thing
"""


def _run(root, *args):
    subprocess.run(("git", "-C", str(root), *args), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A plugin checkout with an upstream, on main, clean, and projected.

    The upstream is a bare repo beside it rather than a mock: the driver's whole
    ordering guarantee is an atomic push of two refs, and that is a property of
    git rather than of this code. Asserting it against something that only
    records calls would prove nothing."""
    upstream = tmp_path / "upstream.git"
    _run(tmp_path, "init", "--quiet", "--bare", str(upstream))

    root = tmp_path / "widget"
    root.mkdir()
    _run(root, "init", "--quiet", "--initial-branch=main")
    _run(root, "config", "user.email", "t@example.com")
    _run(root, "config", "user.name", "Test")

    (root / "plugin.yml").write_text(PLUGIN_YML)
    (root / "CHANGELOG.md").write_text(CHANGELOG)
    from shipyard import gen_plugin_json
    gen_plugin_json.run(root)

    _run(root, "add", "-A")
    _run(root, "commit", "--quiet", "-m", "Initial")
    _run(root, "tag", "v1.2.0")
    _run(root, "remote", "add", "origin", str(upstream))
    _run(root, "push", "--quiet", "-u", "origin", "main", "--tags")
    return root


def _land(root, *subjects):
    for i, subject in enumerate(subjects):
        (root / f"file{i}.txt").write_text(subject)
        _run(root, "add", "-A")
        _run(root, "commit", "--quiet", "-m", subject)
    _run(root, "push", "--quiet", "origin", "main")


@pytest.fixture(autouse=True)
def stub_gh(monkeypatch):
    """`gh`, recorded rather than run.

    Only the two calls the driver makes are stubbed — an auth check and a publish
    — so a test that reaches a third one fails on the unexpected argv rather than
    passing quietly."""
    calls = []

    def fake(root, *args):
        calls.append(args)
        if args[:2] == ("auth", "status"):
            return "logged in"
        if args[0] == "release" and args[1] == "create":
            return f"https://github.com/someone/widget/releases/tag/{args[2]}"
        raise AssertionError(f"unexpected gh call: {args}")

    monkeypatch.setattr(cut, "_gh", fake)
    return calls


# ---- where gh acts ---------------------------------------------------------

def test_gh_runs_inside_the_target_checkout(tmp_path, monkeypatch):
    """The one call that isn't targeted by an explicit flag.

    `git` gets `-C root` everywhere, so a release cut with `--root` tags and
    pushes the right repo no matter where it was invoked from. `gh` reads its
    repo off the working directory instead, so without this it would publish the
    notes against whatever repo the shell was sitting in — which is a public
    release on a repo nobody was releasing.
    """
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(argv, 0, stdout="logged in\n", stderr="")

    monkeypatch.setattr(cut.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    target = tmp_path / "elsewhere"
    target.mkdir()
    _real_gh(target, "auth", "status")

    assert seen["argv"] == ("gh", "auth", "status")
    assert seen["cwd"] == target


# ---- the draft half --------------------------------------------------------

def test_an_absent_section_is_drafted_from_the_commits_since_the_last_tag(repo, capsys):
    _land(repo, "Teach the parser about groups", "Stop dropping the last flag")

    assert cut.run(repo) == 0

    body = changelog.staged_body(repo)
    assert changelog.DRAFT_MARKER in body
    assert "Teach the parser about groups" in body
    assert "Stop dropping the last flag" in body
    # The previous release's section is left where it was, below the new one.
    text = (repo / "CHANGELOG.md").read_text()
    assert text.index("## Unreleased") < text.index("## 1.2.0")
    assert "Preamble that the release" in text


def test_the_draft_stops_short_of_publishing(repo, stub_gh):
    _land(repo, "A change")
    cut.run(repo)
    assert not any(c[0] == "release" for c in stub_gh)
    assert not git.tag_exists(repo, "v1.3.0")


def test_nothing_landed_since_the_last_release_is_not_a_release(repo):
    with pytest.raises(SystemExit, match="nothing has landed"):
        cut.run(repo)


def test_a_worksheet_is_never_redrafted_over_without_asking(repo):
    _land(repo, "A change")
    cut.run(repo)
    # Someone has begun sorting it, and their work is still uncommitted. A second
    # run reaches the ship half and refuses the worksheet by name; what it must
    # not do is drop a fresh worksheet on top of the work in progress.
    with pytest.raises(SystemExit, match="still the drafted worksheet"):
        cut.run(repo)
    assert changelog.DRAFT_MARKER in changelog.staged_body(repo)


def test_draft_replaces_the_section_when_asked_to(repo):
    _land(repo, "First change")
    cut.run(repo)
    _land(repo, "Second change")

    assert cut.run(repo, draft_only=True) == 0
    body = changelog.staged_body(repo)
    assert "Second change" in body
    assert body.count(changelog.DRAFT_MARKER) == 1


# ---- the ship half ---------------------------------------------------------

def _write_notes(root, body):
    """Notes in the file, uncommitted — which is where the draft half leaves them
    and what the ship half is expected to pick up."""
    changelog.write_staged(body, root, force=True)


def test_the_tag_names_a_commit_that_already_carries_the_version(repo, stub_gh):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing you can now do")

    assert cut.run(repo, yes=True) == 0

    # Read the three artifacts *at the tag*, which is the thing that was broken:
    # the commit the tag names has to carry the new version and its own section.
    at_tag = git.run(repo, "show", "v1.3.0:.claude-plugin/plugin.json")
    assert '"version": "1.3.0"' in at_tag
    assert "version: 1.3.0" in git.run(repo, "show", "v1.3.0:plugin.yml")
    assert "## 1.3.0" in git.run(repo, "show", "v1.3.0:CHANGELOG.md")


def test_the_published_body_is_the_committed_section(repo, stub_gh, tmp_path):
    _land(repo, "A change")
    _write_notes(repo, "### Fixed\n\n- The bug that ate your config")

    cut.run(repo, yes=True)

    publish = next(c for c in stub_gh if c[0] == "release")
    notes = pathlib.Path(publish[publish.index("--notes-file") + 1])
    # Deleted after the publish, so compare against what the commit says instead —
    # which is the stronger assertion anyway.
    assert not notes.exists()
    assert changelog.section("1.2.1", repo) == "### Fixed\n\n- The bug that ate your config"


def test_the_branch_and_the_tag_reach_the_upstream_together(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")

    cut.run(repo, yes=True)

    upstream = repo.parent / "upstream.git"
    assert git.run(upstream, "rev-parse", "v1.3.0") == git.run(upstream, "rev-parse", "main")


@pytest.mark.parametrize("notes,expected", [
    ("### Added\n\n- A thing", "1.3.0"),
    ("### Fixed\n\n- A bug", "1.2.1"),
    ("### Removed\n\n- A thing that is gone", "2.0.0"),
    ("### Added\n\n- New\n\n### Removed\n\n- Gone", "2.0.0"),
    ("- An unheaded list", "1.2.1"),
])
def test_the_level_comes_from_the_headings_the_notes_use(repo, notes, expected):
    _land(repo, "A change")
    _write_notes(repo, notes)

    cut.run(repo, yes=True)
    assert git.tag_exists(repo, f"v{expected}")


def test_an_empty_heading_left_by_the_skeleton_does_not_decide_the_level(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n### Fixed\n\n- The only real entry")

    cut.run(repo, yes=True)
    assert git.tag_exists(repo, "v1.2.1")


def test_bump_overrides_what_the_headings_imply(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Fixed\n\n- A bug, but a breaking one")

    cut.run(repo, bump="major", yes=True)
    assert git.tag_exists(repo, "v2.0.0")


def test_a_worksheet_is_refused_as_notes(repo, stub_gh):
    _land(repo, "A change")
    cut.run(repo)

    with pytest.raises(SystemExit, match="still the drafted worksheet"):
        cut.run(repo, yes=True)
    assert not any(c[0] == "release" for c in stub_gh)


def test_a_version_already_released_is_refused(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")
    _run(repo, "tag", "v1.3.0")

    with pytest.raises(SystemExit, match="v1.3.0 already exists"):
        cut.run(repo, yes=True)


def test_nothing_is_written_when_the_confirmation_is_declined(repo, monkeypatch):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")
    before = (repo / "CHANGELOG.md").read_text()
    monkeypatch.setattr("builtins.input", lambda _: "n")

    with pytest.raises(SystemExit, match="stopped"):
        cut.run(repo)

    assert (repo / "CHANGELOG.md").read_text() == before
    assert not git.tag_exists(repo, "v1.3.0")


def test_no_terminal_and_no_yes_stops_rather_than_assuming(repo, monkeypatch):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")

    def no_tty(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_tty)
    with pytest.raises(SystemExit, match="no terminal to confirm on"):
        cut.run(repo)


def test_an_override_at_the_prompt_asks_to_see_that_plan_first(repo, monkeypatch):
    _land(repo, "A change")
    _write_notes(repo, "### Fixed\n\n- A bug")
    monkeypatch.setattr("builtins.input", lambda _: "major")

    assert cut.run(repo) == 1
    assert not git.tag_exists(repo, "v2.0.0")
    assert not git.tag_exists(repo, "v1.2.1")


# ---- the preflight ---------------------------------------------------------

def test_a_dirty_tree_outside_the_changelog_is_refused(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")
    (repo / "plugin.yml").write_text(PLUGIN_YML.replace("A widget", "Edited"))

    with pytest.raises(SystemExit, match="uncommitted changes to plugin.yml"):
        cut.run(repo, yes=True)


def test_the_release_commit_carries_the_notes_that_were_never_committed(repo):
    """The two halves hand off through the working tree, so a release run right
    after a draft has to fold the uncommitted notes into its own commit."""
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing you can now do")
    assert git.dirty_paths(repo) == ["CHANGELOG.md"]

    cut.run(repo, yes=True)

    assert git.dirty_paths(repo) == []
    assert "A thing you can now do" in git.run(repo, "show", "v1.3.0:CHANGELOG.md")
    assert git.run(repo, "log", "-1", "--format=%s") == "Release v1.3.0"


def test_notes_committed_and_pushed_ahead_of_time_release_the_same_way(repo):
    _land(repo, "A change")
    changelog.write_staged("### Added\n\n- A thing", repo, force=True)
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Notes for the next release")
    _run(repo, "push", "--quiet", "origin", "main")

    assert cut.run(repo, yes=True) == 0
    assert "## 1.3.0" in git.run(repo, "show", "v1.3.0:CHANGELOG.md")


def test_an_unpushed_commit_is_refused(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Notes, not pushed")

    with pytest.raises(SystemExit, match="unpushed commit"):
        cut.run(repo, yes=True)


def test_releasing_from_another_branch_is_refused(repo):
    _run(repo, "switch", "--quiet", "-c", "topic")
    with pytest.raises(SystemExit, match="a release is cut from 'main'"):
        cut.run(repo, yes=True)


def test_a_stale_plugin_json_is_refused_as_the_projection_job_s_work(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")
    target = repo / ".claude-plugin" / "plugin.json"
    target.write_text(target.read_text().replace('"A widget"', '"Stale"'))
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Hand-edited projection")
    _run(repo, "push", "--quiet", "origin", "main")

    with pytest.raises(SystemExit, match="plugin.json does not match its source"):
        cut.run(repo, yes=True)


def test_a_repo_with_no_changelog_says_what_is_missing(repo):
    (repo / "CHANGELOG.md").unlink()
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Drop it")
    _run(repo, "push", "--quiet", "origin", "main")

    with pytest.raises(SystemExit, match="no CHANGELOG.md"):
        cut.run(repo, yes=True)


# ---- the major alias -------------------------------------------------------

SHIPYARD_PYPROJECT = '[project]\nname = "shipyard"\nversion = "2.1.0"\n'


@pytest.fixture
def tooling_repo(tmp_path):
    """A repo whose consumers pin it by ref, so its release moves a `vX` alias."""
    upstream = tmp_path / "up.git"
    _run(tmp_path, "init", "--quiet", "--bare", str(upstream))
    root = tmp_path / "tooling"
    root.mkdir()
    _run(root, "init", "--quiet", "--initial-branch=main")
    _run(root, "config", "user.email", "t@example.com")
    _run(root, "config", "user.name", "Test")
    (root / "pyproject.toml").write_text(SHIPYARD_PYPROJECT)
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 2.1.0\n\n- Previous\n")
    _run(root, "add", "-A")
    _run(root, "commit", "--quiet", "-m", "Initial")
    _run(root, "tag", "v2.1.0")
    _run(root, "tag", "v2")
    _run(root, "remote", "add", "origin", str(upstream))
    _run(root, "push", "--quiet", "-u", "origin", "main", "--tags")
    return root


def test_the_major_alias_follows_the_newest_release_on_its_line(tooling_repo):
    _land(tooling_repo, "A change")
    _write_notes(tooling_repo, "### Added\n\n- A thing")

    assert cut.run(tooling_repo, yes=True) == 0

    upstream = tooling_repo.parent / "up.git"
    assert git.run(upstream, "rev-parse", "v2") == git.run(upstream, "rev-parse", "v2.2.0")


def test_the_alias_reads_past_itself_to_find_the_last_release(tooling_repo):
    """`v2` sits on the same commit as `v2.1.0`, so a bare describe answers `v2`.

    That would make the range `v2..HEAD` and the draft empty. The tag reader has
    to match release tags only."""
    _land(tooling_repo, "A change")
    assert git.last_release_tag(tooling_repo) == "v2.1.0"


def test_an_alias_that_is_also_a_branch_is_refused_before_anything_is_written(
        tooling_repo):
    _land(tooling_repo, "A change")
    _write_notes(tooling_repo, "### Removed\n\n- A thing")
    upstream = tooling_repo.parent / "up.git"
    _run(upstream, "branch", "v3", "main")
    before = (tooling_repo / "pyproject.toml").read_text()

    with pytest.raises(SystemExit, match="branch named v3 exists"):
        cut.run(tooling_repo, yes=True)

    # The refusal this replaces fired *after* the bump commit already existed.
    assert (tooling_repo / "pyproject.toml").read_text() == before
    assert not git.tag_exists(tooling_repo, "v3.0.0")


def test_a_plugin_release_moves_no_alias(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")

    cut.run(repo, yes=True)
    assert not git.tag_exists(repo, "v1")


# ---- the toolchain a release must not need ---------------------------------

BROKEN_CLI = """\
name: widget
version: 1.2.0
description: A widget
author: Someone
repository: https://github.com/someone/widget
cli:
  invoke: node dist/cli.js
  engine: usage-lines
  manifest: spec/cli.yml
"""


def test_a_cli_that_cannot_run_does_not_stop_a_release(repo):
    """The failure this design removes.

    The step this replaces ran the full `generate` inside the release, on a
    checkout with no build ahead of it. A plugin whose committed entry point
    imports its dependencies at runtime exited non-zero there, and the release
    died before committing the version bump. Nothing in a release may invoke the
    thing being released."""
    (repo / "plugin.yml").write_text(BROKEN_CLI)
    (repo / "spec").mkdir()
    (repo / "spec" / "cli.yml").write_text("# a manifest no local run can verify\n")
    from shipyard import gen_plugin_json
    gen_plugin_json.run(repo)
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Declare a CLI")
    _run(repo, "push", "--quiet", "origin", "main")
    _write_notes(repo, "### Added\n\n- A thing")

    # `node dist/cli.js` does not exist in this checkout. The release must not care.
    assert not (repo / "dist").exists()
    assert cut.run(repo, yes=True) == 0
    assert "## 1.3.0" in git.run(repo, "show", "v1.3.0:CHANGELOG.md")
    # Untouched: verifying it would mean running the CLI.
    assert (repo / "spec" / "cli.yml").read_text() == \
        "# a manifest no local run can verify\n"


def test_a_stale_hooks_json_is_refused_too(repo):
    (repo / "hooks").mkdir()
    (repo / "hooks" / "hooks.yml").write_text(
        "hooks:\n  - event: PostToolUse\n    command: echo hi\n")
    from shipyard import gen_hooks_json
    gen_hooks_json.run(repo)
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Add a hook")
    _run(repo, "push", "--quiet", "origin", "main")

    target = repo / "hooks" / "hooks.json"
    target.write_text(target.read_text().replace("echo hi", "echo drifted"))
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "Hand-edit the projection")
    _run(repo, "push", "--quiet", "origin", "main")
    _write_notes(repo, "### Added\n\n- A thing")

    with pytest.raises(SystemExit, match="hooks/hooks.json does not match"):
        cut.run(repo, yes=True)


def test_a_plugin_with_no_hooks_yml_has_nothing_to_disagree_with(repo):
    _land(repo, "A change")
    _write_notes(repo, "### Added\n\n- A thing")
    assert not (repo / "hooks").exists()

    assert cut.run(repo, yes=True) == 0


def test_the_preview_explains_an_inferred_level_and_an_override_differently(
        repo, capsys, monkeypatch):
    """A heading is rendered as one; a flag is not.

    The live run of this printed ``from `### --bump` `` — the override's reason
    dressed up as a heading in the notes, which is the one thing it isn't."""
    _land(repo, "A change")
    _write_notes(repo, "### Fixed\n\n- A bug")
    monkeypatch.setattr("builtins.input", lambda _: "n")

    with pytest.raises(SystemExit):
        cut.run(repo)
    assert "(patch, from `### Fixed`)" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cut.run(repo, bump="major")
    assert "(major, from --bump)" in capsys.readouterr().out
