import pytest

from shipyard import build_docs

# gen_plugin_docs, which build_docs finishes with, requires a suite: block.
PLUGIN_YML = "name: demo\nsuite: {sessions: []}\n"


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

    build_docs.run(root, ["art"])

    assert (root / "docs" / "diagram.png").exists()
    assert not (root / "docs" / "hero.svg").exists()


def test_a_declared_path_that_does_not_exist_fails_loudly(plugin):
    root, write = plugin
    write("docs/README.md", "# demo")

    with pytest.raises(SystemExit, match="declared resource path not found: art"):
        build_docs.run(root, ["art"])


def test_a_resource_path_outside_the_plugin_is_refused(plugin):
    root, write = plugin
    write("docs/README.md", "# demo")

    with pytest.raises(SystemExit, match="must be inside the plugin"):
        build_docs.run(root, ["../elsewhere"])


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

    with pytest.raises(SystemExit, match="below docs/"):
        build_docs.run(root, ["."])


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


def _home_plugin(tmp_path, plugin_yml=HOME_YML):
    (tmp_path / "plugin.yml").write_text(plugin_yml)
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.yml").write_text(HOOKS_YML)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# demo\n")
    build_docs.run(tmp_path)
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


def test_resources_from_env_splits_on_newlines_and_commas(monkeypatch):
    monkeypatch.setenv("SHIPYARD_RESOURCES", "assets\n  art  ,\n\nimages\n")

    assert build_docs.resources_from_env() == ["assets", "art", "images"]


def test_an_unset_env_means_the_default_applies_not_publish_nothing(monkeypatch):
    monkeypatch.delenv("SHIPYARD_RESOURCES", raising=False)

    assert build_docs.resources_from_env() is None
