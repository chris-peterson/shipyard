"""A source file whose top level is the wrong type.

`yaml.safe_load(...) or {}` reads an empty file as an empty mapping, which is
right, and says nothing about a file that parsed into a list or a string. That
used to reach whichever generator dereferenced it first and surface as
`AttributeError: 'list' object has no attribute 'get'`, naming a line of shipyard
rather than the file someone has to fix.

Both places that message lands are non-interactive — a CI log, or a plugin
author's terminal running the CLI over their own repo — so each case here asserts
the file is named and the expected shape is stated. Neither reader has shipyard's
source to consult.

Checking that source is well-formed enough to project was `preview.yml`'s stated
job before CI became the writer; deleting it moved the check nowhere.
"""
import pytest

from shipyard import _aggregate, _common, build_docs, gen_hooks_json

PLUGIN_YML = "name: demo\nsuite: {sessions: []}\n"


def _plugin(tmp_path, plugin_yml=PLUGIN_YML):
    (tmp_path / "plugin.yml").write_text(plugin_yml)
    return tmp_path


def _hooks(tmp_path, text):
    (tmp_path / "hooks").mkdir(exist_ok=True)
    path = tmp_path / "hooks" / "hooks.yml"
    path.write_text(text)
    return path


# ---- a whole file of the wrong shape ---------------------------------------

def test_a_hooks_yml_written_as_a_bare_list_names_the_file_and_the_shape(tmp_path):
    """The mistake that motivated this: `hooks.yml` as a top-level list, which is
    how the file reads in the docs once you skip the `hooks:` key."""
    path = _hooks(tmp_path, "- event: SessionStart\n  command: hooks/hello.sh\n")

    with pytest.raises(SystemExit) as exc:
        gen_hooks_json.build(tmp_path)

    assert "hooks.yml" in str(exc.value)
    assert "a mapping with a `hooks:` list" in str(exc.value)
    assert "list" in str(exc.value)


def test_a_plugin_yml_of_the_wrong_shape_names_plugin_yml(tmp_path):
    (tmp_path / "plugin.yml").write_text("- name: demo\n")

    with pytest.raises(SystemExit, match=r"plugin\.yml must be a mapping"):
        _common.load_plugin(tmp_path)


def test_a_plugins_yml_of_the_wrong_shape_names_plugins_yml(tmp_path):
    (tmp_path / "plugins.yml").write_text("- anchor\n- beacon\n")

    with pytest.raises(SystemExit, match=r"plugins\.yml must be a mapping"):
        _aggregate.load_manifest(tmp_path)


def test_an_empty_file_is_still_an_empty_mapping(tmp_path):
    """The `or {}` behavior this replaces has to survive: empty is not malformed,
    and a plugin with no hooks declared is ordinary."""
    path = _hooks(tmp_path, "")

    assert gen_hooks_json.load_hooks(path) == []


# ---- a block of the wrong shape, one level in ------------------------------

def test_a_docs_block_written_as_a_list_names_the_key(tmp_path):
    root = _plugin(tmp_path, PLUGIN_YML + "docs:\n  - mermaid\n")

    with pytest.raises(SystemExit, match=r"`docs:` must be a mapping"):
        build_docs.run(root)


def test_a_hooks_key_that_is_not_a_list_is_refused(tmp_path):
    path = _hooks(tmp_path, "hooks: SessionStart\n")

    with pytest.raises(SystemExit, match=r"`hooks:` must be a list"):
        gen_hooks_json.load_hooks(path)


def test_a_hook_entry_that_is_not_a_mapping_is_refused(tmp_path):
    """A list of plain strings under `hooks:` is the shape you get from writing
    the events out and meaning to fill them in."""
    path = _hooks(tmp_path, "hooks:\n  - SessionStart\n  - PreToolUse\n")

    with pytest.raises(SystemExit, match="hook entry that is a str"):
        gen_hooks_json.load_hooks(path)


# ---- one reader, so one rejection -----------------------------------------

def test_every_hooks_yml_reader_rejects_the_same_shape(tmp_path):
    """build-docs and gen-describe read hooks.yml too. They come through
    `load_hooks`, so a shape one rejects is rejected by all of them rather than by
    whichever projection happened to run first."""
    from shipyard import gen_describe

    root = _plugin(tmp_path)
    path = _hooks(tmp_path, "- event: SessionStart\n")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "README.md").write_text("# demo")

    for call in (lambda: build_docs.run(root),
                 lambda: gen_describe.derive(root),
                 lambda: gen_hooks_json.build(root)):
        with pytest.raises(SystemExit, match="a mapping with a `hooks:` list"):
            call()
