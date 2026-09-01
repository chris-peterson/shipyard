import pytest

from shipyard import build_docs

# gen_plugin_docs, which build_docs finishes with, requires a suite: block.
PLUGIN_YML = "name: demo\nsuite: {sessions: []}\n"


def declare_resources(root, *paths):
    """Point the plugin's `docs: resources:` at `paths` — where the build reads
    them from, so a test that declares them exercises the same path CI does."""
    (root / "plugin.yml").write_text(
        PLUGIN_YML + "docs:\n  resources:\n"
        + "".join(f"    - {p}\n" for p in paths))


@pytest.fixture
def plugin(tmp_path):
    """A plugin root with the minimum build_docs needs, plus a helper to seed
    files by relative path. Returns (root, write)."""
    (tmp_path / "plugin.yml").write_text(PLUGIN_YML)

    def write(rel, text=""):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path
    return tmp_path, write


def test_default_publishes_assets_flattened_to_the_docs_root(plugin):
    root, write = plugin
    write("assets/hero.svg", "<svg/>")
    write("docs/README.md", '<img src="hero.svg">')

    build_docs.run(root)

    assert (root / "docs" / "hero.svg").read_text() == "<svg/>"


def test_a_plugin_with_no_assets_dir_still_builds(plugin):
    root, write = plugin
    write("docs/README.md", "# demo")

    assert build_docs.run(root) == 0


def test_declared_paths_replace_the_default(plugin):
    root, write = plugin
    write("art/diagram.png", "png")
    write("assets/hero.svg", "<svg/>")
    write("docs/README.md", '<img src="diagram.png">')
    declare_resources(root, "art")

    build_docs.run(root)

    assert (root / "docs" / "diagram.png").exists()
    assert not (root / "docs" / "hero.svg").exists()


def test_a_declared_path_that_does_not_exist_fails_loudly(plugin):
    root, write = plugin
    write("docs/README.md", "# demo")
    declare_resources(root, "art")

    with pytest.raises(SystemExit, match="declared resource path not found: art"):
        build_docs.run(root)


def test_a_resource_path_outside_the_plugin_is_refused(plugin):
    root, write = plugin
    write("docs/README.md", "# demo")
    declare_resources(root, "../elsewhere")

    with pytest.raises(SystemExit, match="must be inside the plugin"):
        build_docs.run(root)


def test_a_reference_the_published_tree_cannot_resolve_fails_the_build(plugin):
    """The tack-hero failure: a green deploy and a blank image. Nothing else in
    the build reports it, so this check is the only thing standing between a
    missing file and a shipped 404."""
    root, write = plugin
    write("docs/README.md", '<img src="hero.svg">')

    with pytest.raises(SystemExit, match=r"hero\.svg"):
        build_docs.run(root)


def test_a_markdown_image_is_checked_too(plugin):
    root, write = plugin
    write("docs/README.md", "![the fleet](images/demo.png)")

    with pytest.raises(SystemExit, match=r"images/demo\.png"):
        build_docs.run(root)


def test_a_nested_page_resolves_against_the_docs_root(plugin):
    """docsify is configured with relativePath: false, and a raw <img src>
    resolves against index.html's URL because the route lives in the hash. So a
    skill page reaching for hero.svg gets docs/hero.svg, not a sibling of itself
    — which is what makes a flattened assets/ reachable from every page."""
    root, write = plugin
    write("assets/hero.svg", "<svg/>")
    write("docs/skills/thing.md", '<img src="hero.svg">')

    assert build_docs.run(root) == 0


def test_a_file_beside_a_nested_page_does_not_satisfy_its_reference(plugin):
    """The inverse, and the reason page-relative resolution can't be the model:
    this renders a blank image live, so a check that passed it would be waving
    through the exact failure it exists to catch."""
    root, write = plugin
    write("docs/skills/shot.png", "png")
    write("docs/skills/thing.md", '<img src="shot.png">')

    with pytest.raises(SystemExit, match=r"shot\.png"):
        build_docs.run(root)


def test_a_percent_encoded_reference_resolves_to_the_file_it_names(plugin):
    root, write = plugin
    write("assets/my hero.png", "png")
    write("docs/README.md", "![hero](my%20hero.png)")

    assert build_docs.run(root) == 0


def test_a_resource_path_containing_docs_is_refused(plugin):
    root, write = plugin
    write("docs/README.md", "# demo")
    declare_resources(root, ".")

    with pytest.raises(SystemExit, match="below docs/"):
        build_docs.run(root)


def test_a_projected_artifact_wins_a_collision_with_a_resource(plugin):
    """Copy order decides who wins, so it is pinned here rather than left to the
    order the steps happen to sit in."""
    root, write = plugin
    (root / "plugin.yml").write_text(PLUGIN_YML + "docs: {}\n")
    write("assets/index.html", "from assets")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    assert "from assets" not in (root / "docs" / "index.html").read_text()


HOME_YML = """\
name: demo
version: 2.1.0
repository: https://github.com/chris-peterson/demo
suite:
  cli: true
  gloss: one line about demo
  pitch: the punchy one
  cmds:
    - ["/demo:build", "Build the thing"]
  describe:
    skills:
      build: Build the thing, from its own frontmatter.
      audit: Audit the thing.
    rules:
      stay-put: Stay put
    hooks:
      hooks: 'Hook wiring: SessionStart→greet.'
      greet: SessionStart — greets.
  dependencies:
    - name: moor
      reason: review backend
    - name: revdiff
      url: https://revdiff.com
      reason: alternate backend
"""


HOOKS_YML = """\
hooks:
  - event: SessionStart
    command: 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/greet.sh"'
    description: greets.
"""


def _home_plugin_root(tmp_path, plugin_yml=HOME_YML):
    (tmp_path / "plugin.yml").write_text(plugin_yml)
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.yml").write_text(HOOKS_YML)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# demo\n")
    # The sources behind the describe: entries. A row links only where the build
    # publishes a page, so the artifacts a home-page test is about have to exist.
    for skill in ("build", "audit"):
        (tmp_path / "skills" / skill).mkdir(parents=True)
        (tmp_path / "skills" / skill / "SKILL.md").write_text(f"# {skill}\n")
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "stay-put.md").write_text("# stay put\n")
    return tmp_path


def _home_plugin(tmp_path, plugin_yml=HOME_YML):
    build_docs.run(_home_plugin_root(tmp_path, plugin_yml))
    return (tmp_path / "docs" / "_home.md").read_text()


@pytest.fixture
def home(tmp_path):
    """A plugin whose suite: exercises every section of the home page."""
    return _home_plugin(tmp_path)


def test_the_home_page_leads_with_the_version_and_the_pitch(home):
    assert '<p class="ph-lede">one line about demo</p>' in home
    assert "the punchy one" in home


def test_the_version_tag_goes_to_the_published_release(home):
    assert ('<a class="ph-tag" href="https://github.com/chris-peterson/demo/releases/latest">'
            "v2.1.0</a>") in home


def test_a_cli_plugin_is_marked_ahead_of_its_version(home):
    """Same order as the catalog card, so the two surfaces read alike."""
    assert '<span class="ph-tag ph-cli">cli</span><a class="ph-tag"' in home


def test_the_marks_row_is_also_published_on_its_own(tmp_path):
    """For a home page written by hand, which wants the row and not the page."""
    root = _home_plugin_root(tmp_path)
    build_docs.run(root)
    tags = (root / "docs" / "_tags.md").read_text()

    assert '<span class="ph-tag ph-cli">cli</span><a class="ph-tag"' in tags
    assert ".ph-tags{" in tags, "the row carries the styles it needs"
    assert "## Install" not in tags, "the row, not the generated home page"


def test_a_plugin_with_nothing_to_mark_publishes_no_row(tmp_path):
    root = _home_plugin_root(
        tmp_path, HOME_YML.replace("  cli: true\n", "").replace("version: 2.1.0\n", ""))
    build_docs.run(root)

    assert not (root / "docs" / "_tags.md").exists()


def test_the_cli_mark_goes_to_the_reference_page_where_there_is_one(tmp_path):
    root = _home_plugin_root(tmp_path)
    (root / "docs" / "cli.md").write_text("# demo\n")
    build_docs.run(root)

    assert ('<a class="ph-tag ph-cli" href="#/cli">cli</a>'
            in (root / "docs" / "_home.md").read_text())


def test_a_plugin_that_ships_no_cli_carries_no_mark(tmp_path):
    home = _home_plugin(tmp_path, HOME_YML.replace("  cli: true\n", ""))

    assert '<span class="ph-tag ph-cli">cli</span>' not in home


def test_a_repo_with_no_derivable_releases_url_states_the_version_plainly(tmp_path):
    home = _home_plugin(tmp_path, HOME_YML.replace("github.com", "git.example.com"))

    assert '<span class="ph-tag">v2.1.0</span>' in home


def test_the_gloss_is_a_lede_not_a_blockquote(home):
    """A blockquote renders as the theme's tip callout, which files the plugin's
    one-line summary as an aside."""
    assert "> one line about demo" not in home


def test_a_hook_links_to_its_section_on_the_hooks_page(home):
    """Not to the script on the forge: a reader following a hook from the docs
    should land in the docs."""
    assert "| [`greet`](/hooks?id=greet) |" in home


def test_the_hooks_page_carries_the_wiring_and_the_script(tmp_path):
    _home_plugin(tmp_path)
    (tmp_path / "hooks" / "greet.sh").write_text("#!/usr/bin/env bash\necho hi\n")
    build_docs.run(tmp_path)

    page = (tmp_path / "docs" / "hooks.md").read_text()

    assert "## greet" in page
    assert "| `SessionStart` | — |" in page
    assert "echo hi" in page


def test_a_plugin_with_no_hooks_renders_no_hooks_page(tmp_path):
    (tmp_path / "plugin.yml").write_text("name: demo\nsuite: {gloss: g}\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# demo\n")

    build_docs.run(tmp_path)

    assert not (tmp_path / "docs" / "hooks.md").exists()


def test_a_peer_in_the_suite_carries_its_own_mark(home):
    assert 'src="https://chris-peterson.github.io/moor/favicon.svg"' in home


def test_a_project_documented_off_the_hub_gets_the_outbound_arrow_and_no_mark(home):
    assert "[revdiff](https://revdiff.com) ↗" in home
    assert "revdiff/favicon.svg" not in home


def test_externals_sort_below_the_peers_whatever_order_they_are_declared_in(home):
    """revdiff is declared first; a reader can act on a peer without leaving the
    docs, so the peers lead."""
    assert home.index("[moor]") < home.index("[revdiff]")


def test_a_skill_reads_as_the_command_you_type_and_links_to_its_page(home):
    assert "| [`/demo:build`](/skills/build) |" in home


def test_the_curated_cmds_copy_wins_over_the_generated_description(home):
    """`cmds` is what the author wrote for a reader; the describe: text is
    projected from the skill's own frontmatter, which addresses the agent."""
    assert "| [`/demo:build`](/skills/build) | Build the thing |" in home
    assert "from its own frontmatter" not in home
    # a skill cmds says nothing about keeps the description projected from it
    assert "| [`/demo:audit`](/skills/audit) | Audit the thing. |" in home


def test_the_cmds_order_leads_and_the_rest_follow(home):
    assert home.index("/demo:build") < home.index("/demo:audit")


SAME_NAME_YML = """\
name: demo
suite:
  cmds:
    - ["/demo:demo", "Label a pane, or set status with a note"]
    - ["demo", "Read the resolved project / task / status anywhere"]
  describe:
    skills:
      demo: From the skill's own frontmatter.
"""


def test_a_cli_sharing_a_skills_name_does_not_title_the_skills_row(tmp_path):
    """A plugin can ship a skill and a CLI of the same name, and their `cmds`
    copy addresses different readers: one a session, one someone at a terminal.
    The skill's row carries the skill's line, and the CLI's reaches no table."""
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text("# demo\n")
    home = _home_plugin(tmp_path, SAME_NAME_YML)

    assert "| [`/demo:demo`](/skills/demo) | Label a pane, or set status with a note |" in home
    assert "Read the resolved project" not in home


SKILL_AND_COMMAND_YML = """\
name: demo
suite:
  describe:
    skills:
      sync: What the skill does.
    commands:
      sync: What the command does.
"""


def test_a_skill_and_a_command_of_one_name_keep_their_own_descriptions(tmp_path):
    (tmp_path / "skills" / "sync").mkdir(parents=True)
    (tmp_path / "skills" / "sync" / "SKILL.md").write_text("# sync\n")
    home = _home_plugin(tmp_path, SKILL_AND_COMMAND_YML)

    assert "| [`/demo:sync`](/skills/sync) | What the skill does. |" in home
    assert "| `sync` | What the command does. |" in home


def test_the_wiring_entry_leads_the_hooks_section_instead_of_posing_as_a_hook(home):
    """gen-describe files hooks.json under the reserved name `hooks`; a row
    called `hooks` in a table of hooks reads as a hook the plugin doesn't have."""
    assert "Hook wiring: SessionStart→greet." in home
    assert "| `hooks` |" not in home


def test_a_dependency_off_the_hub_uses_its_declared_url(home):
    assert "[revdiff](https://revdiff.com)" in home
    assert "[moor](https://chris-peterson.github.io/moor)" in home


def test_a_description_that_wraps_or_carries_a_pipe_stays_in_its_cell(tmp_path):
    (tmp_path / "plugin.yml").write_text(
        "name: demo\nsuite:\n  describe:\n    rules:\n      pipes: \"a | b\\nwrapped\"\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# demo\n")

    build_docs.run(tmp_path)

    assert "| a \\| b wrapped |" in (tmp_path / "docs" / "_home.md").read_text()


def test_a_reference_inside_a_fenced_example_is_prose_not_a_reference(plugin):
    """anchor's cr-formatting guide shows the reader a Before/After table as a
    fenced sample. Those filenames are illustrative, and failing a build over
    them would make the check unusable for any guide that documents markdown."""
    root, write = plugin
    write("docs/guides/cr.md",
          "Use a table:\n\n  ```markdown\n  | ![Before](before.png) |\n  ```\n")

    assert build_docs.run(root) == 0


def test_a_reference_in_an_inline_code_span_is_prose_too(plugin):
    root, write = plugin
    write("docs/README.md", 'Write `<img src="hero.svg">` to embed it.')

    assert build_docs.run(root) == 0


@pytest.mark.parametrize("ref", [
    "https://example.com/a.png",
    "//example.com/a.png",
    "/js/docsify-shared.js",
    "data:image/svg+xml,<svg/>",
    "#section",
])
def test_references_that_resolve_outside_the_artifact_are_not_checked(plugin, ref):
    root, write = plugin
    write("docs/README.md", f'<img src="{ref}">')

    assert build_docs.run(root) == 0


def test_the_spec_and_the_ledger_are_both_served(plugin):
    root, write = plugin
    write("SPEC.md", "# spec\n")
    write("STATUS.md", "# status\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    assert (root / "docs" / "spec.md").exists()
    assert (root / "docs" / "status.md").exists()


def test_an_earlier_builds_differently_cased_page_is_replaced(plugin):
    """On macOS a write to docs/spec.md lands *in* a leftover docs/SPEC.md, so the
    page is named one way locally and another in CI — and the routes follow."""
    root, write = plugin
    write("SPEC.md", "# spec\n")
    write("docs/SPEC.md", "# stale\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    assert {p.name for p in (root / "docs").glob("*[sS][pP][eE][cC].md")} == {"spec.md"}


def test_a_versioned_spec_is_served_at_its_version(plugin):
    """tack's ledger cites `spec/v1/SPEC.md` — the contract it actually tracks,
    and a path a site carrying only the root spec reaches nothing at."""
    root, write = plugin
    write("spec/v1/SPEC.md", "# the contract\n")
    write("STATUS.md", "Tracking [`spec/v1/SPEC.md`](spec/v1/SPEC.md).\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    assert (root / "docs" / "spec" / "v1.md").exists()
    assert "(/spec/v1)" in (root / "docs" / "status.md").read_text()


def test_a_skills_link_to_a_shared_reference_resolves_on_the_site(plugin):
    """sextant's whole docs site, in one case: three skills defer to one
    procedure under references/, and every one of those links 404'd."""
    root, write = plugin
    write("references/locate-spec.md", "# locate order\n")
    write("skills/spec-req/SKILL.md",
          "---\nname: spec-req\n---\nPer [locate](../../references/locate-spec.md).\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    assert (root / "docs" / "references" / "locate-spec.md").exists()
    assert "[locate](/references/locate-spec)" in (
        root / "docs" / "skills" / "spec-req.md").read_text()


def test_a_skills_own_references_travel_with_it(plugin):
    """logbook's note skill keeps its references beside it rather than in a
    root-level dir, so the published tree has to keep that shape."""
    root, write = plugin
    write("skills/note/references/hand-edit-mode.md", "# hand edit\n")
    write("skills/note/SKILL.md", "See [mode](references/hand-edit-mode.md).\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    assert (root / "docs" / "skills" / "note" / "references" / "hand-edit-mode.md").exists()
    assert "[mode](/skills/note/references/hand-edit-mode)" in (
        root / "docs" / "skills" / "note.md").read_text()


def test_a_link_to_a_page_the_build_does_not_publish_fails_the_build(plugin):
    """The failure mode this check exists for: docsify renders its own 404 inside
    a page that loaded fine, so the deploy is green and only a reader finds out."""
    root, write = plugin
    write("skills/thing/SKILL.md", "See [changes](../../CHANGELOG.md).\n")
    write("docs/README.md", "# demo")

    with pytest.raises(SystemExit, match=r"CHANGELOG\.md"):
        build_docs.run(root)


def test_a_hand_written_page_pointing_at_a_missing_route_fails_too(plugin):
    """sextant's own meta page linked /STATUS while the build published nothing
    at that route."""
    root, write = plugin
    write("docs/meta.md", "The ledger lives at [STATUS.md](/STATUS).")
    write("docs/README.md", "# demo")

    with pytest.raises(SystemExit, match="/STATUS"):
        build_docs.run(root)


def test_a_link_to_an_anchor_the_target_page_lacks_fails_the_build(plugin):
    root, write = plugin
    write("SPEC.md", "# spec\n\n#### `LOCATE-01`\nThe system shall.\n")
    write("docs/README.md", "See [it](/spec?id=locate-99).")

    with pytest.raises(SystemExit, match="locate-99"):
        build_docs.run(root)


def test_a_backticked_requirement_heading_still_answers_to_its_bare_anchor(plugin):
    """sextant heads every requirement with `` `XX-NN` ``; docsify and GitHub both
    drop the code markup when slugging, so SPEC.md#locate-01 keeps resolving."""
    root, write = plugin
    write("SPEC.md", "# spec\n\n#### `LOCATE-01`\nThe system shall.\n")
    write("docs/README.md", "See [it](/spec?id=locate-01).")

    assert build_docs.run(root) == 0


def test_a_described_artifact_with_no_page_reads_as_a_name_not_a_link(tmp_path):
    """`suite.describe` is a committed projection, so between releases it can name
    an artifact whose source is gone. A row linking that is a 404 in the one table
    every reader starts from."""
    (tmp_path / "plugin.yml").write_text(
        "name: demo\nsuite:\n  describe:\n    skills:\n      gone: Retired last week.\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# demo\n")

    build_docs.run(tmp_path)

    home = (tmp_path / "docs" / "_home.md").read_text()
    assert "| `/demo:gone` |" in home
    assert "(/skills/gone)" not in home


def test_declared_resources_reads_the_docs_block():
    assert build_docs.declared_resources({"resources": ["assets", "art"]}) == \
        ["assets", "art"]


def test_a_lone_path_need_not_be_written_as_a_list():
    assert build_docs.declared_resources({"resources": "art"}) == ["art"]


def test_no_declaration_means_the_default_applies_not_publish_nothing():
    assert build_docs.declared_resources({}) is None


def test_a_wrong_typed_resources_value_is_refused():
    with pytest.raises(SystemExit, match="must be a path or a list of paths"):
        build_docs.declared_resources({"resources": {"assets": True}})


def declare_pre_render(root, *commands):
    """Point the plugin's `docs: pre_render:` at `commands` — where the build
    reads them from, so a test that declares them exercises the same path CI
    does."""
    (root / "plugin.yml").write_text(
        PLUGIN_YML + "docs:\n  pre_render:\n"
        + "".join(f"    - {c}\n" for c in commands))


def test_a_pre_render_command_runs_before_the_link_check(plugin):
    """The whole point: a page pre_render writes is on disk by the time the link
    check at the end of run() looks for it, even though nothing here renders it
    itself."""
    root, write = plugin
    write("gen_extra.py", 'open("docs/extra.md", "w").write("# Extra\\n")\n')
    write("docs/README.md", "[extra](/extra)\n")
    declare_pre_render(root, "python3 gen_extra.py")

    assert build_docs.run(root) == 0
    assert (root / "docs" / "extra.md").read_text() == "# Extra\n"


def test_pre_render_commands_run_in_the_declared_order(plugin):
    root, write = plugin
    write("first.py", 'open("out.txt", "w").write("first\\n")\n')
    write("second.py",
          'assert open("out.txt").read() == "first\\n"\n'
          'open("out.txt", "a").write("second\\n")\n')
    write("docs/README.md", "# demo\n")
    declare_pre_render(root, "python3 first.py", "python3 second.py")

    build_docs.run(root)

    assert (root / "out.txt").read_text() == "first\nsecond\n"


def test_a_failing_pre_render_command_stops_the_build(plugin):
    root, write = plugin
    write("docs/README.md", "# demo\n")
    declare_pre_render(root, "python3 -c \"import sys; sys.exit(3)\"")

    with pytest.raises(SystemExit, match="exited 3"):
        build_docs.run(root)


def test_a_pre_render_command_that_cannot_start_fails_loudly(plugin):
    root, write = plugin
    write("docs/README.md", "# demo\n")
    declare_pre_render(root, "no-such-binary-xyz")

    with pytest.raises(SystemExit, match="failed to start"):
        build_docs.run(root)


def test_declared_pre_render_reads_the_docs_block():
    assert build_docs.declared_pre_render(
        {"pre_render": ["python3 a.py", "python3 b.py"]}) == \
        ["python3 a.py", "python3 b.py"]


def test_a_lone_pre_render_command_need_not_be_written_as_a_list():
    assert build_docs.declared_pre_render({"pre_render": "python3 a.py"}) == \
        ["python3 a.py"]


def test_no_pre_render_declaration_means_nothing_runs():
    assert build_docs.declared_pre_render({}) == []


def test_a_wrong_typed_pre_render_value_is_refused():
    with pytest.raises(SystemExit, match="must be a command or a list of commands"):
        build_docs.declared_pre_render({"pre_render": {"a": True}})


def test_a_skill_page_opens_on_the_command_that_runs_it(plugin):
    """The page's reader wants the string to type, and only a fence gets
    docsify's copy button. The body's own H1 stays as the page title."""
    root, write = plugin
    write("skills/build/SKILL.md", "---\nname: build\n---\n# Build The Thing\n\nProse.\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    page = (root / "docs" / "skills" / "build.md").read_text()
    assert page == "# Build The Thing\n\n```text\n/demo:build\n```\n\nProse.\n"


def test_a_skill_body_with_no_h1_leads_with_the_fence(plugin):
    root, write = plugin
    write("skills/build/SKILL.md", "---\nname: build\n---\nStraight into the prose.\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    page = (root / "docs" / "skills" / "build.md").read_text()
    assert page == "```text\n/demo:build\n```\n\nStraight into the prose.\n"


def test_a_skills_own_headings_survive_the_insert(plugin):
    """The fence goes under the title and nowhere else — the body's headings keep
    the anchors its in-page links resolve against."""
    root, write = plugin
    write("skills/build/SKILL.md",
          "---\nname: build\n---\n# Build\n\n## Step one\n\n# Not the title\n")
    write("docs/README.md", "# demo")

    build_docs.run(root)

    page = (root / "docs" / "skills" / "build.md").read_text()
    assert page.count("```text") == 1
    assert "## Step one" in page
    assert "# Not the title" in page
