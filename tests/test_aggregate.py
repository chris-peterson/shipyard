"""The aggregate projection: plugins.yml + the rostered plugins' plugin.yml → the
marketplace manifest and the doc-site data.

Every test builds a real sibling layout under tmp_path, because "the spokes are
checkouts beside the aggregator" is part of the contract, not an implementation
detail.
"""
import json
import textwrap

import pytest
import yaml

from shipyard import _aggregate, cli, gen_deps_json, gen_marketplace_json, gen_plugins_js

HUB = textwrap.dedent("""\
    name: chris-peterson
    description: Chris Peterson's Claude Code plugins
    owner: chris-peterson
    source: https://github.com/{owner}/{name}.git
    plugins:
      - anchor
      - moor
""")


def spoke(**overrides) -> dict:
    spec = {
        "name": "anchor",
        "version": "1.3.0",
        "description": "Consistency across the code-change lifecycle.",
        "author": "chris-peterson",
        "marketplace": {"category": "development",
                        "homepage": "https://chris-peterson.github.io/anchor/#/"},
        "suite": {"group": "record", "pitch": "the permanent record"},
    }
    spec.update(overrides)
    return spec


@pytest.fixture
def hub(tmp_path):
    """A workspace with an aggregator at `hub/` and two plugins beside it. Returns
    the aggregator root; the helpers below rewrite pieces of it per test."""
    root = tmp_path / "hub"
    root.mkdir()
    (root / "plugins.yml").write_text(HUB)
    for name in ("anchor", "moor"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "plugin.yml").write_text(yaml.safe_dump(spoke(name=name)))
    return root


def write_hub(root, **overrides):
    manifest = yaml.safe_load(HUB)
    manifest.update(overrides)
    (root / "plugins.yml").write_text(yaml.safe_dump(manifest))


def write_spoke(root, name, spec):
    (root.parent / name / "plugin.yml").write_text(yaml.safe_dump(spec))


# ---- the roster --------------------------------------------------------------

def test_bare_names_resolve_through_the_source_template(hub):
    assert _aggregate.roster(hub) == [
        ("anchor", "https://github.com/chris-peterson/anchor.git"),
        ("moor", "https://github.com/chris-peterson/moor.git"),
    ]


def test_roster_reads_without_any_plugin_checkout(tmp_path):
    """The sync step calls this to find out what to clone, so it must not touch
    a spoke — nothing is on disk yet when it runs."""
    root = tmp_path / "hub"
    root.mkdir()
    (root / "plugins.yml").write_text(HUB)
    assert [n for n, _ in _aggregate.roster(root)] == ["anchor", "moor"]


def test_roster_order_is_declared_order(hub):
    write_hub(hub, plugins=["moor", "anchor"])
    assert [n for n, _ in _aggregate.roster(hub)] == ["moor", "anchor"]


def test_missing_source_template_is_an_error(hub):
    manifest = yaml.safe_load(HUB)
    del manifest["source"]
    (hub / "plugins.yml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(SystemExit, match="source:"):
        _aggregate.roster(hub)


def test_empty_plugins_list_is_an_error(hub):
    write_hub(hub, plugins=[])
    with pytest.raises(SystemExit, match="no plugins:"):
        _aggregate.roster(hub)


def test_missing_manifest_is_an_error(tmp_path):
    with pytest.raises(SystemExit, match="no plugins.yml"):
        _aggregate.roster(tmp_path)


# Every malformed roster below resolves to something plausible rather than
# something obviously broken, so each would otherwise publish a wrong catalog at
# exit 0 — or fail much later, complaining about a plugin nobody wrote down.

def test_a_scalar_plugins_value_is_not_iterated_as_characters(hub):
    write_hub(hub, plugins="anchor")
    with pytest.raises(SystemExit, match="must be a list of names"):
        _aggregate.roster(hub)


def test_a_mapping_entry_is_rejected_rather_than_formatted_into_the_url(hub):
    write_hub(hub, plugins=[{"name": "vendored", "source": "https://elsewhere/x.git"}])
    with pytest.raises(SystemExit, match="takes plain names"):
        _aggregate.roster(hub)


def test_a_repeated_name_is_an_error(hub):
    """marketplace.json is built from the roster list and the doc-site data from a
    name-keyed map, so a duplicate would publish two entries and one node."""
    write_hub(hub, plugins=["anchor", "moor", "anchor"])
    with pytest.raises(SystemExit, match="lists anchor more than once"):
        _aggregate.roster(hub)


def test_a_template_field_with_nothing_to_fill_it_is_an_error(hub):
    manifest = yaml.safe_load(HUB)
    del manifest["owner"]
    (hub / "plugins.yml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(SystemExit, match=r"references \{owner\}"):
        _aggregate.roster(hub)


def test_an_unknown_template_field_names_itself(hub):
    write_hub(hub, source="https://github.com/{onwer}/{name}.git")
    with pytest.raises(SystemExit, match=r"references \{onwer\}"):
        _aggregate.roster(hub)


def test_a_template_needing_no_owner_resolves_without_one(hub):
    manifest = yaml.safe_load(HUB)
    del manifest["owner"]
    manifest["source"] = "https://git.example/{name}.git"
    (hub / "plugins.yml").write_text(yaml.safe_dump(manifest))
    assert _aggregate.roster(hub)[0] == ("anchor", "https://git.example/anchor.git")


# ---- marketplace.json -------------------------------------------------------

def test_marketplace_entry_is_projected_from_the_plugin(hub):
    out = json.loads(gen_marketplace_json.build(hub))
    assert out["$schema"] == gen_marketplace_json.SCHEMA
    assert out["owner"] == {"name": "chris-peterson"}
    entry = out["plugins"][0]
    assert entry == {
        "name": "anchor",
        "description": "Consistency across the code-change lifecycle.",
        "author": {"name": "chris-peterson"},
        "source": {"source": "url",
                   "url": "https://github.com/chris-peterson/anchor.git"},
        "category": "development",
        "homepage": "https://chris-peterson.github.io/anchor/#/",
    }


def test_entry_field_order_is_stable(hub):
    """Field order is part of the artifact: the manifest is committed, so a
    reordering would churn the diff on every regeneration."""
    entry = json.loads(gen_marketplace_json.build(hub))["plugins"][0]
    assert list(entry) == ["name", "description", "author", "source",
                           "category", "homepage"]


def test_a_rostered_plugin_with_no_descriptor_fails_loudly(hub):
    (hub.parent / "moor" / "plugin.yml").unlink()
    with pytest.raises(SystemExit, match="moor is on the roster"):
        gen_marketplace_json.build(hub)


def test_a_plugin_without_a_description_fails_loudly(hub):
    spec = spoke(name="moor")
    del spec["description"]
    write_spoke(hub, "moor", spec)
    with pytest.raises(SystemExit, match="no description:"):
        gen_marketplace_json.build(hub)


def test_optional_entry_fields_are_omitted_when_absent(hub):
    write_spoke(hub, "moor", spoke(name="moor", marketplace={"category": "development"}))
    entry = json.loads(gen_marketplace_json.build(hub))["plugins"][1]
    assert "homepage" not in entry
    assert entry["category"] == "development"


def test_a_plugin_with_no_marketplace_block_still_projects(hub):
    spec = spoke(name="moor")
    del spec["marketplace"]
    write_spoke(hub, "moor", spec)
    entry = json.loads(gen_marketplace_json.build(hub))["plugins"][1]
    assert list(entry) == ["name", "description", "author", "source"]


def test_missing_marketplace_identity_is_an_error(hub):
    manifest = yaml.safe_load(HUB)
    del manifest["description"]
    (hub / "plugins.yml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(SystemExit, match="missing description"):
        gen_marketplace_json.build(hub)


# ---- docs/plugins.js --------------------------------------------------------

def plugins_of(body: str) -> dict:
    """The PLUGINS object out of the generated module, which also declares GROUPS."""
    return json.loads(body.split("const PLUGINS = ", 1)[1]
                          .split(";\nconst GROUPS", 1)[0])


def test_plugins_js_projects_the_suite_block_plus_version(hub):
    body = gen_plugins_js.build(hub)
    assert body.startswith("// Generated by shipyard gen-plugins-js")
    plugins = plugins_of(body)
    assert plugins["anchor"]["pitch"] == "the permanent record"
    assert plugins["anchor"]["version"] == "1.3.0"
    assert list(plugins) == ["anchor", "moor"]


def test_a_plugin_without_a_suite_block_fails_loudly(hub):
    spec = spoke(name="moor")
    del spec["suite"]
    write_spoke(hub, "moor", spec)
    with pytest.raises(SystemExit, match="no suite: block"):
        gen_plugins_js.build(hub)


def test_components_come_from_the_declared_artifact_log(hub):
    (hub / "artifacts.csv").write_text(
        "plugin,date,change\n"
        "anchor,2026-01-01,+skill:commit +skill:draft\n"
        "anchor,2026-02-01,-skill:draft +skill:prepare-review +hook:preview\n")
    write_hub(hub, artifacts="artifacts.csv")
    plugins = plugins_of(gen_plugins_js.build(hub))
    assert plugins["anchor"]["components"] == {
        "skills": ["commit", "prepare-review"],
        "hooks": ["preview"],
    }
    # a plugin absent from the log renders without a component list, rather than
    # with an empty one
    assert "components" not in plugins["moor"]


def test_no_declared_log_means_no_component_data(hub):
    assert _aggregate.components(hub) == {}


def test_a_declared_log_that_is_missing_is_an_error(hub):
    write_hub(hub, artifacts="suite/artifacts.csv")
    with pytest.raises(SystemExit, match="declares artifacts:"):
        _aggregate.components(hub)


# ---- docs/deps.json ---------------------------------------------------------

def test_deps_graph_keeps_off_roster_targets_as_dangling_edges(hub):
    """A plugin can name an optional backend the marketplace doesn't ship. The
    edge survives while `nodes` stays the roster — that gap is how the doc site's
    graph tells a catalog plugin from an outside one."""
    suite = {"group": "record",
             "dependencies": [
                 {"name": "moor", "required": False, "reason": "default backend"},
                 {"name": "revdiff", "required": False, "reason": "alternate backend"},
             ]}
    write_spoke(hub, "anchor", spoke(suite=suite))
    graph = json.loads(gen_deps_json.build(hub))
    assert graph["nodes"] == ["anchor", "moor"]
    assert [e["to"] for e in graph["edges"]] == ["moor", "revdiff"]
    assert graph["edges"][1] == {"from": "anchor", "to": "revdiff",
                                "required": False, "reason": "alternate backend"}


def test_a_plugin_declaring_no_dependencies_contributes_no_edges(hub):
    assert json.loads(gen_deps_json.build(hub))["edges"] == []


# ---- the artifact-log primitives --------------------------------------------

def test_change_tokens_round_trip():
    prev = _aggregate.empty_members()
    prev["skills"].add("address-feedback")
    cur = _aggregate.empty_members()
    cur["skills"].add("resolve-feedback")
    assert _aggregate.change_tokens(prev, cur) == \
        "+skill:resolve-feedback -skill:address-feedback"
    replayed = _aggregate.empty_members()
    replayed["skills"].add("address-feedback")
    _aggregate.apply_tokens(replayed, _aggregate.change_tokens(prev, cur))
    assert replayed == cur


def test_apply_tokens_ignores_unparseable_tokens():
    members = _aggregate.empty_members()
    _aggregate.apply_tokens(members, "not-a-token +skill:ok whatever +bogus:x")
    assert members["skills"] == {"ok"}


# ---- the CLI ----------------------------------------------------------------

def test_generate_dispatches_on_the_manifest_at_the_root(hub):
    assert cli.main(["generate", "--root", str(hub)]) == 0
    assert (hub / ".claude-plugin" / "marketplace.json").exists()
    assert (hub / "docs" / "plugins.js").exists()
    assert (hub / "docs" / "deps.json").exists()


def test_roster_command_prints_tab_separated_pairs(hub, capsys):
    assert cli.main(["roster", "--root", str(hub)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "anchor\thttps://github.com/chris-peterson/anchor.git"
