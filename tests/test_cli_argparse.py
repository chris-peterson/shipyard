import json
import pathlib

import pytest
import yaml

from shipyard import gen_cli_manifest

SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[1] / "docs" / "cli-manifest.v1.json").read_text())

# A real argparse CLI, not a captured transcript: the engine's whole premise is
# that it reads what argparse prints, and a transcript would freeze one version's
# formatting as the thing under test.
CLI = '''
import argparse
p = argparse.ArgumentParser(prog="demo", description={description!r})
p.add_argument("--version", action="store_true")
p.add_argument("--color", choices=["auto", "always", "never"])
sub = p.add_subparsers(dest="cmd")

init = sub.add_parser("init", help="create a route")
init.add_argument("slug")
init.add_argument("--group", metavar="slug")

status = sub.add_parser("status", help="show status")
status.add_argument("slug", nargs="?")
status.add_argument("--all", action="store_true")

add = sub.add_parser("add", help="add a tack, recording every word of the summary "
                                "it is given, which runs long enough to wrap")
add.add_argument("slug")
add.add_argument("words", nargs="+")

pick = sub.add_parser("pick", help="pick a mode")
pick.add_argument("mode", choices=["fast", "slow"])

restore = sub.add_parser("import", help="restore from a file")
group = restore.add_mutually_exclusive_group()
group.add_argument("--merge", action="store_true")
group.add_argument("--replace", action="store_true")

link = sub.add_parser("link", help="manage links")
ops = link.add_subparsers(dest="op")
ops.add_parser("add", help="add a link").add_argument("url")
ops.add_parser("rm", help="remove a link").add_argument("url")

shell = sub.add_parser("completions", help="print shell completions")
shell.add_argument("shell", choices=["zsh"], nargs="?")

p.parse_args()
'''

DESCRIPTION = "a demonstration CLI"


def _plugin(tmp_path, description=DESCRIPTION):
    (tmp_path / "cli.py").write_text(CLI.format(description=description))
    (tmp_path / "plugin.yml").write_text(
        "name: demo\n"
        "suite:\n  sessions: []\n"
        "cli:\n"
        "  invoke: python3 cli.py\n"
        "  engine: argparse\n"
        "  manifest: spec/cli.yml\n")
    return tmp_path


def _manifest(tmp_path):
    gen_cli_manifest.run(tmp_path)
    return yaml.safe_load((tmp_path / "spec" / "cli.yml").read_text())


def _command(manifest, *path):
    node = manifest
    for name in path:
        key = "subcommands" if node is not manifest else "commands"
        node = next(c for c in node[key] if c["name"] == name)
    return node


# ---- the engine's grammar --------------------------------------------------

def test_a_required_positional_and_a_flag_with_an_argument(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "init")["usages"][0]
    assert usage["args"] == [{"name": "slug"}]
    assert usage["flags"] == [{"name": "--group", "arg": "slug"}]


def test_an_optional_positional_and_a_switch(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "status")["usages"][0]
    assert usage["args"] == [{"name": "slug", "optional": True}]
    assert usage["flags"] == [{"name": "--all"}]


def test_a_repeatable_positional_records_both_forms_argparse_prints(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "add")["usages"][0]
    assert usage["args"] == [
        {"name": "slug"},
        {"name": "words"},
        {"name": "words", "optional": True, "repeatable": True},
    ]


def test_a_choice_positional_records_its_alternatives(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "pick")["usages"][0]
    assert usage["args"] == [{"name": "fast|slow", "choices": ["fast", "slow"]}]


def test_a_one_member_choice_is_a_plain_placeholder(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "completions")["usages"][0]
    assert usage["args"] == [{"name": "zsh", "optional": True}]


def test_mutually_exclusive_flags_name_each_other(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "import")["usages"][0]
    assert usage["flags"] == [
        {"name": "--merge", "exclusive_with": ["--replace"]},
        {"name": "--replace", "exclusive_with": ["--merge"]},
    ]


def test_a_nested_subparser_is_probed_for_its_own_grammar(tmp_path):
    link = _command(_manifest(_plugin(tmp_path)), "link")
    assert [c["name"] for c in link["subcommands"]] == ["add", "rm"]
    assert _command(_manifest(_plugin(tmp_path)), "link", "add")["usages"][0] == {
        "summary": "add a link", "args": [{"name": "url"}]}


def test_command_order_follows_the_help_output(tmp_path):
    assert [c["name"] for c in _manifest(_plugin(tmp_path))["commands"]] == [
        "init", "status", "add", "pick", "import", "link", "completions"]


# ---- what the engine leaves out --------------------------------------------

def test_the_help_flag_argparse_adds_to_every_parser_is_not_recorded(tmp_path):
    manifest = _manifest(_plugin(tmp_path))
    flags = [f["name"] for c in manifest["commands"] for u in c["usages"]
             for f in u.get("flags", [])]
    assert "-h" not in flags


def test_the_root_keeps_the_help_flag_it_documents(tmp_path):
    flags = _manifest(_plugin(tmp_path))["usages"][0]["flags"]
    assert flags == [
        {"name": "-h"},
        {"name": "--version"},
        {"name": "--color", "arg": "auto|always|never"},
    ]


# ---- the summaries ---------------------------------------------------------

def test_each_command_carries_the_summary_from_the_subcommand_list(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "init")["usages"][0]
    assert usage["summary"] == "create a route"


def test_a_wrapped_summary_is_rejoined(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "add")["usages"][0]
    assert usage["summary"] == ("add a tack, recording every word of the summary "
                                "it is given, which runs long enough to wrap")


def test_a_one_line_description_is_the_clis_summary(tmp_path):
    assert _manifest(_plugin(tmp_path))["summary"] == DESCRIPTION


def test_a_description_longer_than_a_line_is_left_to_the_lede(tmp_path):
    long = ("a demonstration CLI that describes itself at a length no title slot "
            "can hold, which is what the declared lede exists for")
    assert "summary" not in _manifest(_plugin(tmp_path, description=long))


# ---- failure ---------------------------------------------------------------

def test_help_the_engine_cannot_read_fails_loudly(tmp_path):
    root = _plugin(tmp_path)
    (root / "cli.py").write_text("print('demo, a CLI with no usage line')\n")
    with pytest.raises(SystemExit, match="no `usage:` line"):
        gen_cli_manifest.build(root)


def test_a_probe_that_cannot_run_fails_rather_than_dropping_a_branch(tmp_path):
    root = _plugin(tmp_path)
    (root / "cli.py").write_text(
        "import sys\n"
        "if len(sys.argv) > 2:\n"
        "    sys.exit(0)\n"
        + CLI.format(description=DESCRIPTION))
    with pytest.raises(SystemExit, match="printed nothing"):
        gen_cli_manifest.build(root)


# ---- the recording is still a manifest -------------------------------------

def test_the_generated_manifest_validates_against_the_published_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(_manifest(_plugin(tmp_path)), SCHEMA)


def test_the_docs_page_renders_the_recorded_grammar(tmp_path):
    root = _plugin(tmp_path)
    gen_cli_manifest.run(root)
    page = gen_cli_manifest.docs_page(root)
    assert "demo init <slug> [--group <slug>]" in page
    assert "demo import [--merge|--replace]" in page
    assert "demo link add <url>" in page
    assert "demo pick <fast|slow>" in page
