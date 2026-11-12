"""The machine-readable catalog (docs/catalog.json) and `shipyard list`, which reads it.

The catalog builds from the same sibling layout as every aggregate projection;
`list` reads it from the live site by default, so its fetch is stubbed here and
`--root` exercises the local build.
"""
import json

import pytest

from shipyard import cli, gen_catalog_json, listing

from test_aggregate import hub, spoke, write_hub, write_spoke  # noqa: F401  (fixture)


def test_the_marketplace_leads_and_plugins_follow_in_roster_order(hub):
    data = gen_catalog_json.build_data(hub)
    assert data["schema"] == gen_catalog_json.SCHEMA
    assert [(e["type"], e["name"]) for e in data["entries"]] == [
        ("marketplace", "chris-peterson"), ("plugin", "anchor"), ("plugin", "moor")]
    assert data["entries"][0]["counts"] == {"plugins": 2}


def test_a_plugin_entry_is_read_from_its_own_descriptor(hub):
    entry = gen_catalog_json.build_data(hub)["entries"][1]
    assert entry["category"] == "development"
    assert entry["version"] == "1.3.0"
    assert entry["description"] == "Consistency across the code-change lifecycle."
    assert entry["cli"] is False
    assert entry["homepage"] == "https://chris-peterson.github.io/anchor/#/"


def test_the_title_defaults_to_the_name(hub):
    assert gen_catalog_json.build_data(hub)["title"] == "chris-peterson"
    write_hub(hub, title="bridge.ai")
    assert gen_catalog_json.build_data(hub)["title"] == "bridge.ai"


def test_a_suite_cli_flag_or_a_cli_block_marks_a_cli(hub):
    write_spoke(hub, "anchor", spoke(suite={"group": "record", "cli": True}))
    write_spoke(hub, "moor", spoke(name="moor", cli={"invoke": "moor"}))
    entries = gen_catalog_json.build_data(hub)["entries"]
    assert [e["cli"] for e in entries[1:]] == [True, True]


def test_counts_come_from_the_log_without_the_hooks_wiring_file(hub):
    (hub / "artifacts.csv").write_text(
        "plugin,date,change\n"
        "anchor,2026-01-01,+skill:commit +skill:review +hook:preview +hook:hooks\n")
    write_hub(hub, artifacts="artifacts.csv")
    anchor = gen_catalog_json.build_data(hub)["entries"][1]
    assert anchor["components"] == {"skills": ["commit", "review"], "hooks": ["preview"]}
    assert anchor["counts"] == {"skills": 2, "hooks": 1}


def test_generate_writes_the_catalog_for_an_aggregator(hub):
    assert cli.main(["generate", "--root", str(hub)]) == 0
    written = json.loads((hub / "docs" / "catalog.json").read_text())
    assert written == gen_catalog_json.build_data(hub)


# ---- shipyard list -----------------------------------------------------------

def test_list_prints_a_table_with_contents(hub, capsys):
    (hub / "artifacts.csv").write_text(
        "plugin,date,change\nanchor,2026-01-01,+skill:commit +rule:trailers\n")
    write_hub(hub, artifacts="artifacts.csv", title="bridge.ai")
    assert cli.main(["list", "--root", str(hub)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "bridge.ai"
    assert out[2].split() == ["TYPE", "NAME", "CATEGORY", "VERSION", "CONTENTS", "DESCRIPTION"]
    anchor = next(line for line in out if " anchor " in line)
    assert "1 skill, 1 rule" in anchor and "development" in anchor and "1.3.0" in anchor


def test_list_json_prints_entries_filtered_by_type(hub, capsys):
    assert cli.main(["list", "--root", str(hub), "--json", "--type", "plugin"]) == 0
    entries = json.loads(capsys.readouterr().out)
    assert [e["name"] for e in entries] == ["anchor", "moor"]


def test_list_reads_the_live_catalog_by_default(hub, monkeypatch, capsys):
    seen = []
    catalog = gen_catalog_json.build_data(hub)
    monkeypatch.setattr(listing, "fetch", lambda url: seen.append(url) or catalog)
    assert cli.main(["list", "--json"]) == 0
    assert seen == [listing.DEFAULT_URL]
    assert len(json.loads(capsys.readouterr().out)) == 3


def test_list_refuses_a_catalog_schema_it_does_not_know(monkeypatch):
    monkeypatch.setattr(listing, "fetch", lambda url: {"schema": 99, "entries": []})
    with pytest.raises(SystemExit, match="schema 99"):
        cli.main(["list"])


def test_a_long_description_is_clipped_to_the_width():
    catalog = {"title": "t", "entries": []}
    entry = {"type": "plugin", "name": "x", "description": "word " * 40}
    lines = listing.table(catalog, [entry], width=60).splitlines()
    assert all(len(line) <= 60 for line in lines)
    assert lines[-1].endswith("…")
