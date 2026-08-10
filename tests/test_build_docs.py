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
