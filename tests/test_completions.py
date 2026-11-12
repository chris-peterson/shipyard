"""zsh completion: the generated script offers exactly the parser's commands and
flags, parses as zsh, and installs idempotently.

The script is generated from the parser, so drift needs a generator bug rather
than a forgotten edit — but that bug produces no symptom at a prompt, only a
command quietly missing from <TAB>. Equality, not a subset, so a stale offering
fails as well as a missing one.
"""
import re
import shutil
import subprocess

import pytest

from shipyard import cli, completions


@pytest.fixture
def parser():
    return cli.build_parser()


@pytest.fixture
def script(parser):
    return completions.script(parser)


def _offered(script: str) -> set[str]:
    block = re.search(r"commands=\(\n(.*?)\n      \)", script, re.S).group(1)
    return {re.match(r"\s*'([^:]+):", line).group(1) for line in block.splitlines()}


def test_every_command_is_offered_and_nothing_else(parser, script):
    real = set(completions.commands(parser))
    assert real, "parsed no commands — the comparison would pass vacuously"
    assert _offered(script) == real


def test_every_command_has_an_arm_with_each_of_its_flags(parser, script):
    for name, sub in completions._subparsers(parser).items():
        arm = re.search(rf"^        {re.escape(name)}\)\n(.*?);;", script, re.S | re.M)
        assert arm, f"no case arm for {name}"
        for action in sub._actions:
            for flag in action.option_strings:
                assert flag in arm.group(1), f"{name} {flag} not completed"


def test_the_header_matches_the_installed_filename(script):
    assert script.startswith("#compdef shipyard\n")


def test_dynamic_values_are_wired(script):
    assert "_shipyard_plugins" in script.split("onboarding)")[1].split(";;")[0]
    assert "--root[" in script and "_files -/" in script
    assert "(major minor patch)" in script


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_the_script_parses_as_zsh(script, tmp_path):
    path = tmp_path / "_shipyard"
    path.write_text(script)
    result = subprocess.run(["zsh", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_the_plugin_helper_reads_the_roster(script, tmp_path):
    hub = tmp_path / "hub"
    hub.mkdir()
    (hub / "plugins.yml").write_text(
        "name: x\nplugins:\n  - anchor   # first\n  - beacon\ngroups:\n  - key: a\n")
    helper = script.split("_shipyard_plugins() {")[1].split("\n}\n")[0]
    # stub _describe to print what it would offer
    probe = ("_describe() { print -l -- ${(P)${@[-1]}} }\n"
             f"_shipyard_plugins() {{{helper}\n}}\n"
             "words=(shipyard onboarding --root " + str(hub) + " ''); CURRENT=5\n"
             "_shipyard_plugins\n")
    result = subprocess.run(["zsh", "-fc", probe], capture_output=True, text=True)
    assert result.stdout.split() == ["anchor", "beacon"], result.stderr


@pytest.mark.parametrize("before, expect", [
    ("", "fpath and compinit"),
    ("export X=1\nautoload -Uz compinit && compinit\n", "before compinit"),
    ("fpath=(~/.zsh/completions $fpath)\nautoload -Uz compinit && compinit\n", "already"),
])
def test_install_wires_fpath_before_compinit(parser, tmp_path, before, expect):
    if before:
        (tmp_path / ".zshrc").write_text(before)
    report = completions.install(parser, home=tmp_path)
    assert expect in report[1]
    rc = (tmp_path / ".zshrc").read_text()
    assert rc.index(".zsh/completions") < rc.index("compinit")
    assert (tmp_path / ".zsh" / "completions" / "_shipyard").read_text() == \
        completions.script(parser)
    # idempotent: a second run changes nothing
    again = completions.install(parser, home=tmp_path)
    assert again[0].startswith("unchanged") and "already" in again[1]
    assert (tmp_path / ".zshrc").read_text() == rc


def test_print_writes_the_script_to_stdout(capsys, parser):
    assert cli.main(["completions", "zsh", "--print"]) == 0
    assert capsys.readouterr().out == completions.script(parser)
