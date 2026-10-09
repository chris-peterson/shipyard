"""The gate over `claude plugin validate`.

The validator itself belongs to Claude Code and isn't on the test runner's PATH,
so `report` is stubbed here with reports captured from a real run. What's under
test is shipyard's verdict on one: which findings fail, which an acceptance
excuses, and what happens to a report it can't read.
"""
import json

import pytest

from shipyard import gen_plugin_json, validate

WARNINGS = """\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

⚠ Found 2 warnings:

  ❯ icon: Unknown field 'icon' (commonly seen in a VS Code/Cursor extension manifest).
  ❯ name: Plugin name "ClaudeWatch" is not kebab-case.

Validating plugin: /repo/CLAUDE.md

⚠ Found 1 warning:

  ❯ root: CLAUDE.md at the plugin root is not loaded as project context.

✔ Validation passed with warnings
"""

ERRORS = """\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

✘ Found 2 errors:

  ❯ name: Plugin name cannot contain spaces. Use kebab-case (e.g., "my-plugin")
  ❯ description: Invalid input: expected string, received number

Validating skill: /repo/skills/bad/SKILL.md

⚠ Found 1 warning:

  ❯ description: No description in frontmatter.

✘ Validation failed
"""

CLEAN = """\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

✔ Validation passed
"""

# Claude Code 2.1.295 added an advice block, printed after the last section's
# findings. The README path is the finding's field, and the line to paste wraps
# onto the next line.
INSTALL_ADVICE = """\
ℹ Advice (does not change the verdict):

  ❯ /repo/README.md: This README has no line that installs "demo" from a marketplace. Add the install line, which works in one step on Claude Code 2.1.275 or later. Validate the folder that holds its marketplace.json to have <owner>/<repo> filled in, and the name its marketplace lists it under.
      /plugin install demo --marketplace <owner>/<repo>
"""

ADVICE_AFTER_WARNING = f"""\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

Validating plugin: /repo/CLAUDE.md

⚠ Found 1 warning:

  ❯ root: CLAUDE.md at the plugin root is not loaded as project context. To ship context with your plugin, use a skill (skills/<name>/SKILL.md) instead.

{INSTALL_ADVICE}
✔ Validation passed with warnings
"""

ADVICE_ALONE = f"""\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

{INSTALL_ADVICE}
✔ Validation passed
"""

ACCEPT_ROOT = """\
name: demo
validate:
  accept:
    - warning: root
      because: this repo's own agent instructions, not shipped context
"""


def _plugin(tmp_path, plugin_yml="name: demo\n"):
    (tmp_path / "plugin.yml").write_text(plugin_yml)
    return tmp_path


def _stub(monkeypatch, output, code=0):
    monkeypatch.setattr(validate, "report", lambda root: (output, code))


# ---- reading a report ------------------------------------------------------

def test_a_warning_block_and_an_error_block_are_told_apart():
    kinds = {(f.field, f.kind) for f in validate.parse(ERRORS)}
    assert ("name", "error") in kinds
    assert ("description", "error") in kinds
    # Same field name, other block: the skill's `description` is a warning.
    assert sum(1 for f in validate.parse(ERRORS) if f.kind == "warning") == 1


def test_a_finding_carries_the_file_its_section_named():
    by_field = {f.field: f.source for f in validate.parse(WARNINGS)}
    assert by_field["icon"] == "/repo/.claude-plugin/plugin.json"
    assert by_field["root"] == "/repo/CLAUDE.md"


def test_the_trailer_is_not_read_as_a_block_header():
    """`✘ Validation failed` shares its mark with an error header. Counting it
    as one would attach the next report's findings to a block that ended."""
    assert len(validate.parse(ERRORS)) == 3


def test_a_wrapped_finding_keeps_its_whole_message():
    wrapped = WARNINGS.replace(
        "  ❯ root: CLAUDE.md at the plugin root is not loaded as project context.",
        "  ❯ root: CLAUDE.md at the plugin root is not loaded\n"
        "    as project context.")
    root = next(f for f in validate.parse(wrapped) if f.field == "root")
    assert root.message.endswith("as project context.")


def test_a_clean_report_has_no_findings():
    assert validate.parse(CLEAN) == []


def test_advice_after_a_warning_block_is_advice_not_a_warning():
    kinds = {f.field: f.kind for f in validate.parse(ADVICE_AFTER_WARNING)}
    assert kinds == {"root": validate.WARNING,
                     "/repo/README.md": validate.ADVICE}


def test_advice_with_no_block_before_it_is_advice_not_an_error():
    [advice] = validate.parse(ADVICE_ALONE)
    assert advice.kind == validate.ADVICE
    assert advice.message.endswith(
        "/plugin install demo --marketplace <owner>/<repo>")


def test_a_block_the_grammar_does_not_name_is_unread():
    """Its findings would otherwise take the kind of the block before it."""
    renamed = ADVICE_AFTER_WARNING.replace(
        "ℹ Advice (does not change the verdict):", "★ Notes:")
    kinds = {f.field: f.kind for f in validate.parse(renamed)}
    assert kinds["/repo/README.md"] == validate.UNREAD


# ---- the verdict -----------------------------------------------------------

def test_a_clean_report_passes(tmp_path, monkeypatch, capsys):
    _stub(monkeypatch, CLEAN)
    assert validate.run(_plugin(tmp_path)) == 0
    assert "passes plugin validation" in capsys.readouterr().out


def test_advice_alone_passes_and_is_counted(tmp_path, monkeypatch, capsys):
    _stub(monkeypatch, ADVICE_ALONE)
    assert validate.run(_plugin(tmp_path)) == 0
    assert "1 piece of advice above, which never gates" in capsys.readouterr().out


def test_advice_after_an_accepted_warning_passes(tmp_path, monkeypatch, capsys):
    _stub(monkeypatch, ADVICE_AFTER_WARNING)
    assert validate.run(_plugin(tmp_path, ACCEPT_ROOT)) == 0
    assert ("1 accepted warning; 1 piece of advice"
            in capsys.readouterr().out)


def test_advice_is_not_listed_with_the_warnings_that_fail(tmp_path, monkeypatch):
    _stub(monkeypatch, ADVICE_AFTER_WARNING)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path))
    assert "root" in str(exc.value)
    assert "README" not in str(exc.value)


def test_a_finding_in_an_unknown_block_fails_naming_the_block(
        tmp_path, monkeypatch):
    """A validator release that adds a block shipyard doesn't read can't pass
    the gate silently, and can't fail it as an error it never reported."""
    _stub(monkeypatch, ADVICE_AFTER_WARNING.replace(
        "ℹ Advice (does not change the verdict):", "★ Notes:"))
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, ACCEPT_ROOT))
    assert "'★ Notes:'" in str(exc.value)
    assert "cannot tell whether it gates" in str(exc.value)


def test_an_unaccepted_warning_fails_and_says_where_to_accept_it(
        tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path))
    assert "icon" in str(exc.value)
    assert "validate: accept:" in str(exc.value)


def test_an_accepted_warning_passes(tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    accepted = _plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
      because: cosmetic
    - warning: name
      because: renaming breaks installed copies
    - warning: root
      because: this repo's own agent instructions, not shipped context
""")
    assert validate.run(accepted) == 0


def test_an_error_is_never_excused_by_an_acceptance(tmp_path, monkeypatch):
    """An unknown field is a judgment call; a wrong-typed one is a broken
    plugin. Only the first is something a plugin gets to stand behind."""
    _stub(monkeypatch, ERRORS, code=1)
    accepted = _plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: name
      because: we like it this way
    - warning: description
      because: and this
""")
    with pytest.raises(SystemExit) as exc:
        validate.run(accepted)
    assert "Plugin name cannot contain spaces" in str(exc.value)


def test_an_acceptance_can_be_narrowed_to_one_file(tmp_path, monkeypatch):
    """`description` names both a manifest error and a skill warning in one
    report, so an unqualified acceptance is broader than its reason."""
    _stub(monkeypatch, WARNINGS)
    narrowed = _plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
      path: .claude-plugin/plugin.json
      because: cosmetic
    - warning: name
      path: .claude-plugin/plugin.json
      because: renaming breaks installed copies
    - warning: root
      path: CLAUDE.md
      because: this repo's own agent instructions
""")
    assert validate.run(narrowed) == 0


def test_an_acceptance_narrowed_to_the_wrong_file_does_not_apply(
        tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
      path: docs/plugin-docs.json
      because: cosmetic
"""))
    assert "icon" in str(exc.value)


def test_an_acceptance_that_matches_nothing_fails(tmp_path, monkeypatch):
    """The reason it records has outlived the warning it explains, and the next
    reader would take it for a live exception."""
    _stub(monkeypatch, CLEAN)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
      because: cosmetic
"""))
    assert "no longer reports" in str(exc.value)


def test_a_nonzero_exit_with_no_readable_error_fails_loudly(
        tmp_path, monkeypatch):
    """A report format shipyard no longer reads. The validator objected to
    something and shipyard can't say what, so it can't report a pass."""
    _stub(monkeypatch, ERRORS.replace("❯", "*"), code=1)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path))
    assert "names no error shipyard could read" in str(exc.value)


def test_a_run_that_reaches_no_verdict_is_not_a_pass(tmp_path, monkeypatch):
    """A first-run banner, a stub on PATH, a build that exits 0 having done
    nothing — each reads as a clean pass from the exit code alone."""
    _stub(monkeypatch, "Welcome to Claude Code! Run /login to get started.\n")
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path))
    assert "without reaching a verdict" in str(exc.value)


# ---- the acceptance block's own shape --------------------------------------

def test_an_acceptance_with_no_reason_is_rejected(tmp_path, monkeypatch):
    """Indistinguishable from a warning somebody silenced to get a build green."""
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
"""))
    assert "/because is required" in str(exc.value)


def test_a_misspelled_acceptance_field_is_rejected(tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
      reason: cosmetic
"""))
    assert "is not an acceptance field" in str(exc.value)


def test_accept_written_as_a_mapping_names_the_shape(tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, """\
name: demo
validate:
  accept:
    icon: cosmetic
"""))
    assert "must be a list" in str(exc.value)


def test_validate_written_as_a_list_names_the_file_and_the_shape(
        tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, "name: demo\nvalidate:\n  - icon\n"))
    assert "`validate:` must be a mapping" in str(exc.value)


def test_the_same_warning_accepted_twice_is_rejected(tmp_path, monkeypatch):
    _stub(monkeypatch, WARNINGS)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path, """\
name: demo
validate:
  accept:
    - warning: icon
      because: cosmetic
    - warning: icon
      because: cosmetic, again
"""))
    assert "a second time" in str(exc.value)


# ---- what the projection puts in front of the validator ---------------------

def test_a_field_the_runtime_does_not_read_stays_out_of_plugin_json(tmp_path):
    """`icon:` in plugin.yml feeds nothing in plugin.json that Claude Code is
    known to read, so projecting it would ship a value that does nothing."""
    plugin = _plugin(tmp_path, "name: demo\nversion: 1.0.0\nicon: docs/favicon.svg\n")
    assert "icon" not in json.loads(gen_plugin_json.build(plugin))


def test_listing_urls_reach_plugin_json(tmp_path):
    """The validator recognizes these listing keys, so a plugin.yml that
    declares one ships it rather than losing it silently."""
    urls = {
        "documentationUrl": "https://example.com/docs",
        "supportUrl": "https://example.com/support",
        "privacyPolicyUrl": "https://example.com/privacy",
        "termsOfServiceUrl": "https://example.com/terms",
    }
    body = "name: demo\nversion: 1.0.0\n" + "".join(f"{k}: {v}\n" for k, v in urls.items())
    projected = json.loads(gen_plugin_json.build(_plugin(tmp_path, body)))
    assert {k: projected.get(k) for k in urls} == urls


def test_documentation_url_defaults_to_the_homepage(tmp_path):
    body = ("name: demo\nversion: 1.0.0\n"
            "marketplace:\n  homepage: https://example.com/demo/#/\n")
    projected = json.loads(gen_plugin_json.build(_plugin(tmp_path, body)))
    assert projected["documentationUrl"] == "https://example.com/demo/#/"


def test_a_declared_documentation_url_wins_over_the_homepage(tmp_path):
    body = ("name: demo\nversion: 1.0.0\ndocumentationUrl: https://example.com/docs\n"
            "marketplace:\n  homepage: https://example.com/demo/#/\n")
    projected = json.loads(gen_plugin_json.build(_plugin(tmp_path, body)))
    assert projected["documentationUrl"] == "https://example.com/docs"


@pytest.mark.parametrize("value", [42, "docs/support", "ftp://example.com/x"])
def test_a_listing_url_that_is_not_a_url_is_rejected(tmp_path, value):
    """The validator passes these unchecked, so the projection is the gate."""
    plugin = _plugin(tmp_path, f"name: demo\nversion: 1.0.0\nsupportUrl: {value}\n")
    with pytest.raises(SystemExit, match="supportUrl must be an http"):
        gen_plugin_json.build(plugin)


# ---- the validator's absence -----------------------------------------------

def test_a_missing_claude_names_what_to_install(tmp_path, monkeypatch):
    monkeypatch.setattr(validate.shutil, "which", lambda tool: None)
    with pytest.raises(SystemExit) as exc:
        validate.run(_plugin(tmp_path))
    assert "@anthropic-ai/claude-code" in str(exc.value)
