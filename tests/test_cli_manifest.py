import json
import pathlib

import pytest
import yaml

from shipyard import build_docs, cli, gen_cli_manifest

SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[1] / "docs" / "cli-manifest.v1.json").read_text())

# One synthetic CLI carrying every construct the usage-lines engine claims to
# read, so a grammar case that regresses names itself in the failure.
HELP = """demo — a demonstration CLI

Usage:
  demo init <slug> [--group <slug>]
  demo status [slug] [--all]
  demo status set <slug> <state> <pending|done>
  demo move <src>/<id> <dst>
  demo merge <new> <src>... [--break-deps]
  demo serve install|uninstall [--port <n>]
  demo find --url <url> [--json]     Find by URL
  demo find --path [<dir>] [--json]  Find by path
  demo import <file> [--merge|--replace]   (merge is the default)
  demo add <slug> [--link "label,url"]...
  demo link add <slug> <url>
  demo link rm <slug> <url>
  demo completions zsh
  demo pack [<file>...]
  demo config [--global] set <key> <value>
  demo audit     --since <date> [--json]     Audit since a date
  demo --version
"""


def _plugin(tmp_path, help_text=HELP, cli_block=True):
    """A plugin root whose declared CLI prints `help_text`."""
    (tmp_path / "cli.py").write_text(
        "import sys\nsys.stdout.write(%r)\n" % help_text)
    block = (
        "cli:\n"
        "  invoke: python3 cli.py\n"
        "  engine: usage-lines\n"
        "  manifest: spec/v1/cli.yml\n"
    ) if cli_block else ""
    (tmp_path / "plugin.yml").write_text(f"name: demo\nsuite: {{sessions: []}}\n{block}")
    return tmp_path


def _manifest(tmp_path):
    gen_cli_manifest.run(tmp_path)
    return yaml.safe_load((tmp_path / "spec" / "v1" / "cli.yml").read_text())


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


def test_an_unbracketed_placeholder_is_an_optional_positional(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "status")["usages"][0]

    assert usage["args"] == [{"name": "slug", "optional": True}]
    assert usage["flags"] == [{"name": "--all"}]


def test_a_second_line_sharing_a_prefix_becomes_a_subcommand(tmp_path):
    manifest = _manifest(_plugin(tmp_path))

    assert [a["name"] for a in _command(manifest, "status", "set")["usages"][0]["args"]] \
        == ["slug", "state", "pending|done"]


def test_an_alternation_records_its_choices(tmp_path):
    manifest = _manifest(_plugin(tmp_path))
    arg = _command(manifest, "status", "set")["usages"][0]["args"][2]

    assert arg["choices"] == ["pending", "done"]


def test_an_alternation_in_the_command_path_records_its_choices(tmp_path):
    serve = _command(_manifest(_plugin(tmp_path)), "serve", "install|uninstall")

    assert serve["choices"] == ["install", "uninstall"]


def test_a_composite_placeholder_keeps_its_brackets(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "move")["usages"][0]

    assert [a["name"] for a in usage["args"]] == ["<src>/<id>", "dst"]


def test_a_repeatable_positional(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "merge")["usages"][0]

    assert usage["args"][1] == {"name": "src", "repeatable": True}


def test_a_repeatable_flag_keeps_its_argument(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "add")["usages"][0]

    assert usage["flags"] == [{"name": "--link", "arg": "label,url", "repeatable": True}]


def test_an_unbracketed_flag_binds_the_placeholder_after_it(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "find")["usages"][0]

    assert usage["flags"][0] == {"name": "--url", "arg": "url", "required": True}
    assert "args" not in usage  # <url> belongs to --url, not to the command


def test_a_bracketed_placeholder_after_a_flag_stays_a_positional(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "find")["usages"][1]

    assert usage["flags"][0] == {"name": "--path", "required": True}
    assert usage["args"] == [{"name": "dir", "optional": True}]


def test_a_bracketed_repeatable_positional(tmp_path):
    """`[<file>...]` brackets the ellipsis with the placeholder; `[--link <x>]...`
    puts it outside. Reading only the outside form recorded the name as
    `<file>...` and dropped `repeatable`, so a consumer read a single file."""
    usage = _command(_manifest(_plugin(tmp_path)), "pack")["usages"][0]

    assert usage["args"] == [{"name": "file", "optional": True, "repeatable": True}]


def test_a_literal_segment_after_a_flag_stays_a_command_path(tmp_path):
    """A flag between two path segments doesn't end the path. Ending it there
    recorded `set` as a positional, and the reference page then documented an
    arbitrary value where the CLI requires the word."""
    config = _command(_manifest(_plugin(tmp_path)), "config", "set")

    assert [a["name"] for a in config["usages"][0]["args"]] == ["key", "value"]
    assert config["usages"][0]["flags"] == [{"name": "--global"}]


def test_alignment_inside_the_form_does_not_end_the_grammar(tmp_path):
    """Two spaces ordinarily start the summary, but a help block that aligns its
    columns *within* the form would otherwise have its flags read as prose and
    silently dropped."""
    usage = _command(_manifest(_plugin(tmp_path)), "audit")["usages"][0]

    assert usage["summary"] == "Audit since a date"
    assert usage["flags"] == [{"name": "--since", "arg": "date", "required": True},
                              {"name": "--json"}]


def test_an_alternation_of_a_flag_and_a_bare_word_fails_loudly(tmp_path):
    """Recording the bare word as a flag would write a name the published schema
    rejects, and dropping it would lose half the form."""
    root = _plugin(tmp_path, help_text="Usage:\n  demo pick [--json|text]\n")

    with pytest.raises(SystemExit, match="alternation of a flag and a bare word"):
        gen_cli_manifest.run(root)
    assert not (root / "spec" / "v1" / "cli.yml").exists()


def test_two_documented_forms_of_one_command_are_two_usages(tmp_path):
    find = _command(_manifest(_plugin(tmp_path)), "find")

    assert [u["summary"] for u in find["usages"]] == ["Find by URL", "Find by path"]


def test_mutually_exclusive_flags_name_each_other(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "import")["usages"][0]

    assert usage["flags"] == [
        {"name": "--merge", "exclusive_with": ["--replace"]},
        {"name": "--replace", "exclusive_with": ["--merge"]},
    ]


def test_trailing_prose_is_recorded_verbatim(tmp_path):
    usage = _command(_manifest(_plugin(tmp_path)), "import")["usages"][0]

    assert usage["summary"] == "(merge is the default)"


def test_a_command_documented_only_through_its_subcommands_has_no_usages(tmp_path):
    link = _command(_manifest(_plugin(tmp_path)), "link")

    assert "usages" not in link
    assert [c["name"] for c in link["subcommands"]] == ["add", "rm"]


def test_a_documented_leaf_that_takes_nothing_keeps_an_empty_usage(tmp_path):
    """The empty usage is what tells a documented form (`demo completions zsh`)
    apart from a bare grouping node (`demo link`)."""
    zsh = _command(_manifest(_plugin(tmp_path)), "completions", "zsh")

    assert zsh["usages"] == [{}]


def test_a_form_with_no_command_word_is_a_root_usage(tmp_path):
    manifest = _manifest(_plugin(tmp_path))

    assert manifest["usages"] == [{"flags": [{"name": "--version", "required": True}]}]


def test_the_cli_summary_comes_from_the_line_above_the_usage_block(tmp_path):
    assert _manifest(_plugin(tmp_path))["summary"] == "a demonstration CLI"


def test_command_order_follows_the_help_output(tmp_path):
    manifest = _manifest(_plugin(tmp_path))

    assert [c["name"] for c in manifest["commands"]][:4] == \
        ["init", "status", "move", "merge"]


# ---- the declaration -------------------------------------------------------

def test_a_repo_with_no_cli_block_is_unaffected(tmp_path):
    root = _plugin(tmp_path, cli_block=False)

    assert gen_cli_manifest.build(root) is None
    assert gen_cli_manifest.run(root) == 0
    assert not (root / "spec").exists()


def test_a_partial_cli_block_names_what_is_missing(tmp_path):
    (tmp_path / "plugin.yml").write_text(
        "name: demo\ncli:\n  invoke: python3 cli.py\n")

    with pytest.raises(SystemExit, match="missing engine, manifest"):
        gen_cli_manifest.build(tmp_path)


def test_an_unknown_engine_lists_the_known_ones(tmp_path):
    root = _plugin(tmp_path)
    (root / "plugin.yml").write_text(
        (root / "plugin.yml").read_text().replace("usage-lines", "commander"))

    with pytest.raises(SystemExit, match="unknown engine 'commander'.*usage-lines"):
        gen_cli_manifest.build(root)


def test_a_cli_that_cannot_run_fails_loudly(tmp_path):
    root = _plugin(tmp_path)
    (root / "plugin.yml").write_text(
        (root / "plugin.yml").read_text().replace("python3 cli.py", "no-such-binary"))

    with pytest.raises(SystemExit, match="can't run the declared `invoke`"):
        gen_cli_manifest.build(root)


def test_help_the_engine_cannot_parse_writes_no_manifest(tmp_path):
    root = _plugin(tmp_path, help_text="demo: a CLI with no usage block\n")

    with pytest.raises(SystemExit, match="no `Usage:` heading"):
        gen_cli_manifest.run(root)
    assert not (root / "spec" / "v1" / "cli.yml").exists()


def test_a_usage_line_for_another_program_fails_loudly(tmp_path):
    root = _plugin(tmp_path, help_text="Usage:\n  demo init <slug>\n  other run\n")

    with pytest.raises(SystemExit, match="doesn't start with `demo`"):
        gen_cli_manifest.build(root)


def test_a_cli_that_failed_to_start_reports_its_own_error(tmp_path):
    """The exit code can't decide whether help was printed, so a CLI that never
    ran reaches the engine with its error message as the "help output". Reporting
    only the parse failure points the reader at the one thing that isn't wrong —
    the likeliest CI failure for a caller that forgot to build its CLI."""
    root = _plugin(tmp_path)
    (root / "cli.py").write_text(
        "import sys\nsys.stderr.write('Error: Cannot find module dist/cli.js\\n')\n"
        "sys.exit(1)\n")

    with pytest.raises(SystemExit, match="Cannot find module"):
        gen_cli_manifest.build(root)


def test_an_aggregate_repo_declares_no_cli(tmp_path):
    """An aggregator carries plugins.yml and no plugin.yml, so asking it for a
    `cli:` block would fail its projection rather than skip it."""
    (tmp_path / "plugins.yml").write_text("name: hub\nplugins: []\n")

    assert gen_cli_manifest.build(tmp_path) is None
    assert gen_cli_manifest.run(tmp_path) == 0


def test_help_printed_to_stderr_is_still_read(tmp_path):
    root = _plugin(tmp_path)
    (root / "cli.py").write_text("import sys\nsys.stderr.write(%r)\n" % HELP)

    assert _command(_manifest(root), "init")["name"] == "init"


# ---- the projection --------------------------------------------------------

def test_generate_writes_the_manifest(tmp_path):
    root = _plugin(tmp_path)
    (root / "docs").mkdir()

    assert cli.main(["generate", "--root", str(root)]) == 0
    assert (root / "spec" / "v1" / "cli.yml").exists()


# ---- the reference page ----------------------------------------------------

def test_the_docs_page_renders_the_committed_manifest(tmp_path):
    root = _plugin(tmp_path)
    gen_cli_manifest.run(root)
    (root / "docs").mkdir()

    build_docs.run(root)

    page = (root / "docs" / "cli.md").read_text()
    assert "# demo" in page
    assert "demo init <slug> [--group <slug>]" in page


def test_the_docs_page_round_trips_the_trickier_forms(tmp_path):
    root = _plugin(tmp_path)
    gen_cli_manifest.run(root)

    page = gen_cli_manifest.docs_page(root)

    assert "demo move <src>/<id> <dst>" in page
    assert "demo merge <new> <src>... [--break-deps]" in page
    assert "demo import <file> [--merge|--replace]" in page
    assert 'demo add <slug> [--link <label,url>]...' in page
    assert "demo find --url <url> [--json]" in page
    assert "demo find --path [<dir>] [--json]" in page
    assert "demo pack [<file>...]" in page


def test_an_unreadable_committed_manifest_names_itself(tmp_path):
    """build-docs gates the release, so a manifest the renderer can't read has to
    name the file rather than surfacing as a KeyError from inside the docs build."""
    root = _plugin(tmp_path)
    (root / "spec" / "v1").mkdir(parents=True)
    (root / "spec" / "v1" / "cli.yml").write_text("")

    with pytest.raises(SystemExit, match="spec/v1/cli.yml carries no `name`"):
        gen_cli_manifest.docs_page(root)


def test_no_docs_page_before_the_manifest_is_generated(tmp_path):
    assert gen_cli_manifest.docs_page(_plugin(tmp_path)) is None


def test_a_repo_with_no_cli_gets_no_docs_page(tmp_path):
    root = _plugin(tmp_path, cli_block=False)
    (root / "docs").mkdir()

    build_docs.run(root)

    assert not (root / "docs" / "cli.md").exists()


# ---- the published schema --------------------------------------------------

def test_the_generated_manifest_validates_against_the_published_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")

    jsonschema.validate(_manifest(_plugin(tmp_path)), SCHEMA)


def test_the_manifest_points_at_the_schema_that_describes_it(tmp_path):
    assert _manifest(_plugin(tmp_path))["schema"] == SCHEMA["$id"]
