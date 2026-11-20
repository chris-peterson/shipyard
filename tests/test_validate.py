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

# Claude Code 2.1.314 adds a section of the checks Anthropic's plugin directory
# runs, under the same block headers as the validator's own findings.
DIRECTORY_CHECKS = f"""\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

Validating plugin: /repo/CLAUDE.md

⚠ Found 1 warning:

  ❯ root: CLAUDE.md at the plugin root is not loaded as project context. To ship context with your plugin, use a skill (skills/<name>/SKILL.md) instead.

Plugin directory checks for /repo. The plugin directory is the catalog that plugins are submitted to; this is a subset of what it runs.

✘ Found 2 problems the plugin directory refuses a submission for:

  ❯ README.md: README missing (README_MISSING). This plugin has no README.md.
    Fix: Add a README.md to the plugin folder describing what the plugin does.
  ❯ LICENSE: License missing (LICENSE_MISSING). This plugin has no LICENSE file and plugin.json has no `license`.
    Fix: Add a LICENSE file to the plugin folder, or set `license` (an SPDX id) in plugin.json.

⚠ Found 1 plugin directory warning:

  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING). No icon found in the plugin.
    Fix: Add a square PNG to the plugin folder at .claude-plugin/icon.png.

These plugin directory checks do not change the result below.

The directory also runs a safety scan and a policy review that this command does not.

{INSTALL_ADVICE}
✔ Validation passed with warnings
"""

# Claude Code 2.1.326 lists what the plugin provides, and closes the directory
# section's findings with a note on how it ran them. Captured from real runs:
# a plugin with a hook and two skills, and one whose README came from the
# repository root above it.
PROVIDES = """\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

Validating plugin: /repo/CLAUDE.md

⚠ Found 1 warning:

  ❯ root: CLAUDE.md at the plugin root is not loaded as project context. To ship context with your plugin, use a skill (skills/<name>/SKILL.md) instead.

Provides:

  ❯ hooks: PostToolUse Bash command "bash \\"${CLAUDE_PLUGIN_ROOT}/hooks/react.sh\\""
  ❯ skills: mate:feature
  ❯ skills: mate:fix

Plugin directory checks for /repo. The plugin directory is the catalog that plugins are submitted to; this is a subset of what it runs.

✔ These checks found nothing to report

The directory also runs a safety scan and a policy review that this command does not.

✔ Validation passed with warnings
"""

ABOUT_THESE_CHECKS = """\
Validating plugin manifest: /repo/plugin/.claude-plugin/plugin.json

Provides:

  ❯ skills: shipyard:add-plugin
  ❯ skills: shipyard:list

Plugin directory checks for /repo/plugin. The plugin directory is the catalog that plugins are submitted to; this is a subset of what it runs.

⚠ Found 1 plugin directory warning:

  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING). No icon found in the plugin.
    Fix: Add a square PNG to the plugin folder at .claude-plugin/icon.png.

About these checks:

  ❯ The repository root was taken to be /repo, the nearest parent folder with a .git folder or file. README.md was taken from it, because this plugin folder has none of its own. For a plugin submitted from a git repository, the repository root is the top folder of that repository, with only what is committed there, so check that the folder named above is that top folder.

These plugin directory checks do not change the result below.

The directory also runs a safety scan and a policy review that this command does not.

✔ Validation passed
"""

# A plugin with a hooks module, as Claude Code 2.1.329 reports it: the module's
# report sits under hooks.json with no header, and its type check gets a
# section of its own.
MODULE_REPORT = """\
Validating plugin manifest: /repo/.claude-plugin/plugin.json

Validating hooks: /repo/hooks/hooks.json

  ❯ ./switch.ts hooks: session.start, prompt.submit
  ❯ ./switch.ts gating hook without .catch: prompt.submit
  ❯ ./switch.ts calls: $.ui.toast

Validating hooks: /repo/hooks/switch.ts

⚠ Found 1 warning:

  ❯ line 1, column 26: error TS7006: Parameter 'on' implicitly has an 'any' type.

Provides:

  ❯ modules: hooks/switch.ts

✔ Validation passed with warnings
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


def test_plugin_directory_checks_are_their_own_kind():
    """Under the directory section, an error or warning header opens a
    directory block, and the section's path is each finding's source."""
    found = [(f.field, f.kind, f.source) for f in validate.parse(DIRECTORY_CHECKS)]
    assert found == [
        ("root", validate.WARNING, "/repo/CLAUDE.md"),
        ("README.md", validate.DIRECTORY, "/repo"),
        ("LICENSE", validate.DIRECTORY, "/repo"),
        (".claude-plugin/plugin.json icon", validate.DIRECTORY, "/repo"),
        ("/repo/README.md", validate.ADVICE, "/repo"),
    ]


def test_a_block_the_grammar_does_not_name_is_unread():
    """Its findings would otherwise take the kind of the block before it."""
    renamed = ADVICE_AFTER_WARNING.replace(
        "ℹ Advice (does not change the verdict):", "★ Notes:")
    kinds = {f.field: f.kind for f in validate.parse(renamed)}
    assert kinds["/repo/README.md"] == validate.UNREAD


def test_what_a_plugin_provides_is_inventory():
    found = [(f.field, f.kind) for f in validate.parse(PROVIDES)]
    assert found == [
        ("root", validate.WARNING),
        ("hooks", validate.INVENTORY),
        ("skills", validate.INVENTORY),
        ("skills", validate.INVENTORY),
    ]


def test_a_note_on_how_the_directory_checks_ran_is_inventory():
    """It sits inside the directory section, but it's no directory finding."""
    kinds = [f.kind for f in validate.parse(ABOUT_THESE_CHECKS)]
    assert kinds == [validate.INVENTORY, validate.INVENTORY,
                     validate.DIRECTORY, validate.INVENTORY]


def test_a_hooks_modules_report_is_inventory_and_its_type_check_a_warning():
    found = [(f.field, f.kind, f.source) for f in validate.parse(MODULE_REPORT)]
    assert found == [
        ("./switch.ts hooks", validate.INVENTORY, "/repo/hooks/hooks.json"),
        ("./switch.ts gating hook without .catch", validate.INVENTORY,
         "/repo/hooks/hooks.json"),
        ("./switch.ts calls", validate.INVENTORY, "/repo/hooks/hooks.json"),
        ("line 1, column 26", validate.WARNING, "/repo/hooks/switch.ts"),
        ("modules", validate.INVENTORY, "/repo/hooks/switch.ts"),
    ]


def test_a_headerless_line_that_names_no_module_is_still_unread():
    other = MODULE_REPORT.replace("./switch.ts calls", "switch calls")
    kinds = {f.field: f.kind for f in validate.parse(other)}
    assert kinds["switch calls"] == validate.UNREAD


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


def test_plugin_directory_checks_never_gate(tmp_path, monkeypatch, capsys):
    """The validator says they don't change its result, so they don't change
    shipyard's either: not its refusals, and not its warnings."""
    _stub(monkeypatch, DIRECTORY_CHECKS)
    assert validate.run(_plugin(tmp_path, ACCEPT_ROOT)) == 0
    assert "3 plugin directory findings above, which never gate" in capsys.readouterr().out


def test_inventory_never_gates_and_is_not_counted(tmp_path, monkeypatch, capsys):
    """A list of what the plugin provides says nothing is wrong with it."""
    _stub(monkeypatch, PROVIDES)
    assert validate.run(_plugin(tmp_path, ACCEPT_ROOT)) == 0
    out = capsys.readouterr().out
    assert "passes plugin validation (1 accepted warning)." in out


def test_a_note_on_how_the_checks_ran_never_gates(tmp_path, monkeypatch, capsys):
    _stub(monkeypatch, ABOUT_THESE_CHECKS)
    assert validate.run(_plugin(tmp_path)) == 0
    assert ("1 plugin directory finding above, which never gates"
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

def test_the_icon_reaches_plugin_json(tmp_path):
    """Anthropic's directory and marketplace catalogs read `icon` from
    plugin.json, and the validator recognizes it."""
    plugin = _plugin(tmp_path, "name: demo\nversion: 1.0.0\nicon: docs/favicon.svg\n")
    assert json.loads(gen_plugin_json.build(plugin))["icon"] == "docs/favicon.svg"


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
