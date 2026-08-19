"""The composite actions plugins call.

Both actions run shipyard straight out of the checkout the action itself lives
in, by pointing PYTHONPATH at a path relative to `github.action_path`. Nothing
else checks that path: it resolves at runtime, in a caller's repo, and a wrong
one surfaces there as `No module named shipyard` rather than here.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).parents[1]
ACTIONS = sorted(p for p in (ROOT / "actions").glob("*/action.yml"))

PYTHONPATH = re.compile(r"\$\{\{\s*github\.action_path\s*\}\}/(.+)")


def _steps(action):
    return yaml.safe_load(action.read_text())["runs"]["steps"]


def test_every_action_is_discovered():
    assert [p.parent.name for p in ACTIONS] == ["build-docs", "project"]


def test_each_actions_pythonpath_reaches_the_shipyard_package():
    for action in ACTIONS:
        for step in _steps(action):
            declared = (step.get("env") or {}).get("PYTHONPATH")
            if not declared:
                continue
            m = PYTHONPATH.match(declared)
            assert m, f"{action.parent.name}: PYTHONPATH is not action-relative"
            resolved = (action.parent / m.group(1)).resolve()
            assert (resolved / "shipyard" / "__init__.py").exists(), \
                f"{action.parent.name}: PYTHONPATH {declared} misses src/shipyard"


def test_no_action_interpolates_an_input_into_a_shell_script():
    """A workflow input expanded into `run:` is a script-injection surface. Every
    input reaches its step by environment instead."""
    for action in ACTIONS:
        for step in _steps(action):
            script = step.get("run", "")
            assert "inputs." not in script, \
                f"{action.parent.name}: step {step.get('name')!r} interpolates an input"
