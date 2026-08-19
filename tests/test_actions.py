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
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

PYTHONPATH = re.compile(r"\$\{\{\s*github\.action_path\s*\}\}/(.+)")


def _label(path):
    """`build-docs` for an action, `release.yml` for a workflow."""
    return path.parent.name if path.name == "action.yml" else path.name


def _steps(path):
    """Every step, whether the file is a composite action or a workflow."""
    doc = yaml.safe_load(path.read_text()) or {}
    steps = list((doc.get("runs") or {}).get("steps") or [])
    for job in (doc.get("jobs") or {}).values():
        steps += job.get("steps") or []
    return steps


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


def test_nothing_interpolates_an_input_into_a_shell_script():
    """An input expanded into `run:` is a script-injection surface. Every input
    reaches its step by environment instead.

    Workflows are covered alongside the actions: `cut-release.yml` takes a
    dispatch input, so the rule stopped being an actions-only concern the moment
    a workflow had an input of its own to mishandle."""
    for path in ACTIONS + WORKFLOWS:
        for step in _steps(path):
            script = step.get("run", "")
            assert "inputs." not in script, \
                f"{_label(path)}: step {step.get('name')!r} interpolates an input"
