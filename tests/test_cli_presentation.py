"""The declared half of the CLI manifest: the lede, the grouping, the examples.

Help output says what commands exist. It has no way to say which belong
together, what a worked example looks like, or what a reader needs to know
before the first one — so a page rendered from the recording alone is complete
and unreadable, and a page written by hand is readable and silently incomplete.
tack's hand-written reference was missing three of thirty-five commands,
including a whole `repo` family that had shipped a release.

So `plugin.yml` declares the organisation, the recording stays the authority on
what exists, and the generator refuses any disagreement. The ungrouped-command
check is the one that matters: it is how a new command goes undocumented, and it
is the check a hand-written page cannot perform on itself.
"""
import pathlib

import pytest
import yaml

from shipyard import cli, gen_cli_manifest

HELP = """demo — a demonstration CLI

Usage:
  demo init <slug>
  demo list [--json]
  demo nuke <slug> [--force]
"""


def _plugin(tmp_path, cli_block):
    (tmp_path / "cli.py").write_text("import sys\nsys.stdout.write(%r)\n" % HELP)
    (tmp_path / "plugin.yml").write_text(
        "name: demo\nsuite:\n  sessions: []\n" + cli_block)
    return tmp_path


BASE = """cli:
  invoke: python3 cli.py
  engine: usage-lines
  manifest: spec/v1/cli.yml
"""

GROUPED = BASE + """  lede: |
    Slugs are case-sensitive.
  groups:
    - name: Routes
      about: Making and listing things.
      commands: [init, list]
    - name: Danger
      commands: [nuke]
  examples:
    list:
      - run: demo list --json
        note: Machine-readable.
        out: '[]'
"""


def _manifest(root):
    gen_cli_manifest.run(root)
    return yaml.safe_load((root / "spec" / "v1" / "cli.yml").read_text())


# ---- the recording stays the authority ------------------------------------

def test_a_group_naming_an_undocumented_command_is_refused(tmp_path):
    root = _plugin(tmp_path, BASE + """  groups:
    - name: Routes
      commands: [init, list, nuke, teleport]
""")
    with pytest.raises(SystemExit, match="'teleport', which the CLI's help doesn't"):
        gen_cli_manifest.run(root)


def test_a_documented_command_in_no_group_is_refused(tmp_path):
    """The failure this exists for: `nuke` would render nowhere, and nothing
    else in the build would notice."""
    root = _plugin(tmp_path, BASE + """  groups:
    - name: Routes
      commands: [init, list]
""")
    with pytest.raises(SystemExit, match="no group lists: nuke"):
        gen_cli_manifest.run(root)


def test_a_command_in_two_groups_is_refused(tmp_path):
    root = _plugin(tmp_path, BASE + """  groups:
    - name: Routes
      commands: [init, list, nuke]
    - name: Danger
      commands: [nuke]
""")
    with pytest.raises(SystemExit, match="'nuke' is in both"):
        gen_cli_manifest.run(root)


def test_an_example_for_an_undocumented_command_is_refused(tmp_path):
    root = _plugin(tmp_path, BASE + """  examples:
    teleport:
      - run: demo teleport
""")
    with pytest.raises(SystemExit, match="names 'teleport'"):
        gen_cli_manifest.run(root)


def test_an_example_without_a_run_is_refused(tmp_path):
    root = _plugin(tmp_path, BASE + """  examples:
    list:
      - note: no command here
""")
    with pytest.raises(SystemExit, match="needs a `run:`"):
        gen_cli_manifest.run(root)


# ---- what lands in the manifest ------------------------------------------

def test_a_note_for_an_undocumented_command_is_refused(tmp_path):
    root = _plugin(tmp_path, BASE + """  notes:
    teleport: Goes nowhere.
""")
    with pytest.raises(SystemExit, match="`cli: notes:` names 'teleport'"):
        gen_cli_manifest.run(root)


def test_an_empty_note_is_refused(tmp_path):
    root = _plugin(tmp_path, BASE + """  notes:
    list: '   '
""")
    with pytest.raises(SystemExit, match="must be non-empty text"):
        gen_cli_manifest.run(root)


def test_a_note_renders_under_the_command_it_describes(tmp_path):
    """The half of the page no recording can produce: why a command refuses,
    what it stamps, which escape hatch to reach for."""
    root = _plugin(tmp_path, GROUPED + """  notes:
    nuke: |
      Refuses unless `--force`. There is no undo.
""")
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)

    assert "Refuses unless `--force`. There is no undo." in page
    # under its own command, after the grammar
    assert page.index("### `demo nuke`") < page.index("There is no undo")


def test_the_manifest_stays_a_recording(tmp_path):
    """The declared half never lands in the committed manifest.

    Its worth is that a diff in it is a grammar change — a renamed flag reaching
    users with nothing naming it is why it exists. Six hundred lines of prose
    alongside would bury exactly that signal, so the organisation merges at
    render time and the file on disk stays what the binary said."""
    m = _manifest(_plugin(tmp_path, GROUPED))

    assert [c["name"] for c in m["commands"]] == ["init", "list", "nuke"]
    for declared in ("lede", "groups", "examples", "notes"):
        assert declared not in m


def test_the_page_still_gets_both_halves(tmp_path):
    root = _plugin(tmp_path, GROUPED)
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)

    assert "Slugs are case-sensitive." in page          # lede
    assert "## Routes" in page                          # groups
    assert "demo list --json" in page                   # examples
    assert "### `demo nuke`" in page                    # the recording


def test_declaring_no_organisation_still_records_a_valid_grammar(tmp_path):
    """Every manifest written before these fields existed stays valid, which is
    why this is still schema v1."""
    m = _manifest(_plugin(tmp_path, BASE))

    assert [c["name"] for c in m["commands"]] == ["init", "list", "nuke"]
    for key in ("lede", "groups", "examples"):
        assert key not in m


# ---- the page ------------------------------------------------------------

def test_the_page_renders_groups_as_sections_and_commands_beneath(tmp_path):
    root = _plugin(tmp_path, GROUPED)
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)

    assert "## Routes" in page
    assert "### `demo init`" in page
    assert "## Danger" in page
    assert page.index("## Routes") < page.index("## Danger")
    assert "Slugs are case-sensitive." in page


def test_an_example_renders_its_note_command_and_output(tmp_path):
    root = _plugin(tmp_path, GROUPED)
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)

    assert "Machine-readable." in page
    assert "```bash\ndemo list --json\n```" in page


def test_without_groups_the_page_is_a_flat_list_at_h2(tmp_path):
    root = _plugin(tmp_path, BASE)
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)

    assert "## `demo init`" in page
    assert "### `demo init`" not in page


def test_every_recorded_command_reaches_the_grouped_page(tmp_path):
    """The property the coverage check buys: the page can't omit a command."""
    root = _plugin(tmp_path, GROUPED)
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)
    m = yaml.safe_load((root / "spec" / "v1" / "cli.yml").read_text())

    for command in m["commands"]:
        assert f"`demo {command['name']}`" in page


def test_generate_writes_a_grouped_manifest_end_to_end(tmp_path):
    root = _plugin(tmp_path, GROUPED)
    (root / "docs").mkdir()

    assert cli.main(["generate", "--root", str(root)]) == 0

    assert "## Routes" in (root / "docs" / "cli.md").read_text()
