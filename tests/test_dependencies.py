"""Hard dependencies: a plugin's `dependencies:` → its plugin.json, cross-checked
against the marketplace's allowCrossMarketplaceDependenciesOn.

These are the plugins Claude Code installs alongside this one. They are not the
`suite.dependencies:` edges the doc site draws — those are soft: a named backend
a plugin prefers, which nothing installs and whose absence disables nothing. The
two are separate fields for that reason.

`claude plugin validate --strict` passes every shape under "what the manifest
validator lets through" below, so each one surfaces first at install, on a user's
machine, as a resolution error naming a plugin they did not write.
"""
import json
import textwrap

import pytest
import yaml

from shipyard import _validate, gen_marketplace_json, gen_plugin_json

HUB = textwrap.dedent("""\
    name: chris-peterson
    description: Chris Peterson's Claude Code plugins
    owner: chris-peterson
    source: https://github.com/{owner}/{name}.git
    plugins:
      - anchor
""")


@pytest.fixture
def hub(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    (root / "plugins.yml").write_text(HUB)
    (tmp_path / "anchor").mkdir()
    return root


def write_spoke(hub, **extra):
    spec = {
        "name": "anchor",
        "version": "1.3.0",
        "description": "Consistency across the code-change lifecycle.",
        "author": "chris-peterson",
        "marketplace": {"category": "development"},
    }
    spec.update(extra)
    (hub.parent / "anchor" / "plugin.yml").write_text(yaml.safe_dump(spec))
    return hub.parent / "anchor"


def write_hub(hub, **overrides):
    manifest = yaml.safe_load(HUB)
    manifest.update(overrides)
    (hub / "plugins.yml").write_text(yaml.safe_dump(manifest))


def rejects(dependencies, expected, plugin="anchor", allowed=None):
    errors = _validate.dependency_errors(dependencies, plugin, allowed)
    assert any(expected in e for e in errors), \
        f"expected an error mentioning {expected!r}, got: {errors}"


# ---- the projection ---------------------------------------------------------

def test_dependencies_reach_plugin_json(hub):
    spoke = write_spoke(hub, dependencies=[
        "audit-logger", {"name": "secrets-vault", "version": "~2.1.0"}])
    out = json.loads(gen_plugin_json.build(spoke))
    assert out["dependencies"] == [
        "audit-logger", {"name": "secrets-vault", "version": "~2.1.0"}]


def test_dependencies_land_last_in_plugin_json(hub):
    spoke = write_spoke(hub, dependencies=["audit-logger"])
    assert list(json.loads(gen_plugin_json.build(spoke)))[-1] == "dependencies"


def test_a_plugin_declaring_none_publishes_without_the_field(hub):
    spoke = write_spoke(hub)
    assert "dependencies" not in json.loads(gen_plugin_json.build(spoke))


def test_soft_suite_dependencies_are_not_hard_dependencies(hub):
    """The doc-site graph's optional-backend edges install nothing, so they must
    not leak into the manifest Claude Code resolves."""
    spoke = write_spoke(hub, suite={"group": "record", "dependencies": [
        {"name": "revdiff", "required": False, "reason": "preferred backend"}]})
    assert "dependencies" not in json.loads(gen_plugin_json.build(spoke))


def test_a_bad_dependency_names_the_plugin_and_the_field(hub):
    spoke = write_spoke(hub, dependencies=[{"name": "dep", "version": "~>2.1.0"}])
    with pytest.raises(SystemExit, match=r"(?s)dependencies Claude Code cannot resolve.*version"):
        gen_plugin_json.build(spoke)


# ---- what the manifest validator lets through -------------------------------

@pytest.mark.parametrize("version", ["~>2.1.0", "not a range", "2,1,0", "", "v"])
def test_a_version_that_is_not_a_semver_range_is_rejected(version):
    rejects([{"name": "dep", "version": version}], "must be a semver range")


@pytest.mark.parametrize("version", [
    "~2.1.0", "^2.0", ">=1.4", "=2.1.0", "1.2.x", "*",
    ">=1.2 <2.0.0", "1.0.0 - 2.0.0", "^1 || ^2", "^2.0.0-0", ">= 1.2.3",
])
def test_the_documented_range_syntaxes_are_accepted(version):
    assert _validate.dependency_errors([{"name": "dep", "version": version}],
                                       "anchor") == []


def test_a_misspelled_dependency_field_is_rejected():
    """`verison` parses, installs, and silently applies no constraint at all."""
    rejects([{"name": "dep", "verison": "~2.1.0"}],
            "verison is not a dependency field")


def test_a_dependency_on_itself_is_rejected():
    rejects(["anchor"], "lists anchor itself")


def test_a_repeated_dependency_is_rejected():
    rejects(["dep", {"name": "dep", "version": "^2"}], "lists dep more than once")


def test_a_bare_name_is_accepted():
    assert _validate.dependency_errors(["audit-logger"], "anchor") == []


def test_a_dependency_with_no_name_is_rejected():
    rejects([{"version": "~2.1.0"}], "/name is required")


def test_dependencies_that_are_not_a_list_are_rejected():
    rejects("audit-logger", "must be a list")


# ---- the cross-marketplace allowlist ----------------------------------------

def test_an_unallowlisted_marketplace_is_rejected(hub):
    write_spoke(hub, dependencies=[{"name": "dep", "marketplace": "acme-shared"}])
    with pytest.raises(SystemExit, match="(?s)allowCrossMarketplaceDependenciesOn"):
        gen_marketplace_json.build(hub)


def test_an_allowlisted_marketplace_passes_and_is_published(hub):
    write_hub(hub, allowCrossMarketplaceDependenciesOn=["acme-shared"])
    write_spoke(hub, dependencies=[{"name": "dep", "marketplace": "acme-shared"}])
    out = json.loads(gen_marketplace_json.build(hub))
    assert out["allowCrossMarketplaceDependenciesOn"] == ["acme-shared"]


def test_the_allowlist_is_omitted_when_empty(hub):
    write_spoke(hub)
    assert "allowCrossMarketplaceDependenciesOn" not in \
        json.loads(gen_marketplace_json.build(hub))


def test_a_malformed_allowlist_is_an_error(hub):
    write_hub(hub, allowCrossMarketplaceDependenciesOn="acme-shared")
    write_spoke(hub)
    with pytest.raises(SystemExit, match="must be a list of marketplace names"):
        gen_marketplace_json.build(hub)


def test_a_plugin_repo_cannot_answer_the_allowlist_question(hub):
    """gen-plugin-json runs in the spoke, where plugins.yml is out of reach, so
    a cross-marketplace dependency passes there and is caught by the aggregate."""
    spoke = write_spoke(hub, dependencies=[{"name": "dep", "marketplace": "acme-shared"}])
    assert json.loads(gen_plugin_json.build(spoke))["dependencies"]
