"""hooks.yml projected into the hooks.json Claude Code reads."""
import json

import pytest

from shipyard import gen_hooks_json


def _project(tmp_path, text):
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.yml").write_text(text)
    return json.loads(gen_hooks_json.build(tmp_path))


def test_entries_group_by_event_and_matcher_in_order(tmp_path):
    projected = _project(tmp_path, """\
hooks:
  - event: PreToolUse
    matcher: Bash
    command: a.sh
  - event: SessionStart
    command: b.sh
  - event: PreToolUse
    matcher: Bash
    command: c.sh
""")
    assert projected == {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "a.sh"},
            {"type": "command", "command": "c.sh"},
        ]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": "b.sh"}]}],
    }}


def test_per_hook_fields_reach_hooks_json_as_written(tmp_path):
    projected = _project(tmp_path, """\
hooks:
  - event: PreToolUse
    matcher: Bash
    if: Bash(git *)
    command: guard.sh
    timeout: 10
    onFailure: block
    statusMessage: Checking the command
  - event: PostToolUse
    command: node
    args: ["${CLAUDE_PLUGIN_ROOT}/scripts/log.js"]
    async: true
    asyncRewake: false
    shell: bash
""")
    pre = projected["hooks"]["PreToolUse"][0]["hooks"][0]
    post = projected["hooks"]["PostToolUse"][0]["hooks"][0]
    assert pre == {"type": "command", "command": "guard.sh",
                   "if": "Bash(git *)", "timeout": 10, "onFailure": "block",
                   "statusMessage": "Checking the command"}
    assert post == {"type": "command", "command": "node",
                    "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/log.js"],
                    "async": True, "asyncRewake": False, "shell": "bash"}


def test_the_description_stays_in_hooks_yml(tmp_path):
    """gen-describe and build-docs read it from the source; Claude Code has no
    use for it in hooks.json."""
    projected = _project(tmp_path, """\
hooks:
  - event: Stop
    command: stop.sh
    description: Wraps up the turn.
""")
    assert projected["hooks"]["Stop"][0]["hooks"] == [
        {"type": "command", "command": "stop.sh"}]


def test_an_empty_hooks_yml_still_projects_an_empty_hooks_map(tmp_path):
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.yml").write_text("hooks: []\n")
    assert gen_hooks_json.build(tmp_path) == '{\n  "hooks": {}\n}\n'


def test_modules_follow_hooks_in_either_form(tmp_path):
    """A string is the path; a mapping carries a description too, which stays
    in hooks.yml the way a hook entry's does."""
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.yml").write_text("""\
hooks:
  - event: Stop
    command: stop.sh
modules:
  - ./register.ts
  - path: ./switch.tsx
    description: Switches rigs from the prompt.
""")
    text = gen_hooks_json.build(tmp_path)
    assert list(json.loads(text)) == ["hooks", "modules"]
    assert json.loads(text)["modules"] == ["./register.ts", "./switch.tsx"]


def test_a_modules_only_hooks_yml_leaves_hooks_out(tmp_path):
    """The shape Claude Code's own module plugins ship: `{"modules": [...]}`."""
    projected = _project(tmp_path, "modules:\n  - ./register.mjs\n")
    assert projected == {"modules": ["./register.mjs"]}


def test_no_modules_key_leaves_the_projection_as_it_was(tmp_path):
    projected = _project(tmp_path, """\
hooks:
  - event: Stop
    command: stop.sh
modules: []
""")
    assert projected == {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "stop.sh"}]}]}}


def _rejected(tmp_path, text):
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.yml").write_text(text)
    with pytest.raises(SystemExit) as raised:
        gen_hooks_json.build(tmp_path)
    return str(raised.value)


def test_modules_must_be_a_list(tmp_path):
    message = _rejected(tmp_path, "modules: ./register.ts\n")
    assert "`modules:` must be a list of module paths, but it is a str" in message


def test_every_bad_module_entry_is_named_at_once(tmp_path):
    message = _rejected(tmp_path, """\
modules:
  - register.ts
  - ./register.py
  - path: ./ok.js
    descripton: typo
  - path: ""
  - 42
  - path: ./ok.js
    description: ""
""")
    assert "/modules/0 must be relative to hooks/ and start with ./, but it is 'register.ts'" in message
    assert "/modules/1 must name a .ts, .tsx, .js, or .mjs module, but it is './register.py'" in message
    assert "/modules/2/descripton is not a module field (path, description)" in message
    assert "/modules/3/path is required and must be a non-empty string" in message
    assert "/modules/4 must be a path such as ./register.ts" in message
    assert "/modules/5/description must be a non-empty string" in message
    assert "/modules lists ./ok.js more than once" in message
