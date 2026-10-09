"""hooks.yml projected into the hooks.json Claude Code reads."""
import json

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
