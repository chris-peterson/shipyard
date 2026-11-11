"""`shipyard onboarding`: what a plugin still needs before its aggregator ships it.

Two halves. The local checks read the plugin's checkout, the aggregator, and the
hub page it names; the GitHub checks go through `gh`, which these tests replace
with a fake so they run without a network and can say what GitHub returned.
"""
import json
import subprocess
import textwrap

import pytest
import yaml

from shipyard import onboarding

HUB = textwrap.dedent("""\
    name: acme
    owner: acme
    source: https://github.com/{owner}/{name}.git
    plugins:
      - widget
    groups:
      - key: tools
        accent: --tools
        tag: Tools
    hub: ../site/projects.yml
""")

READY = {
    "visibility": "PUBLIC",
    "homepageUrl": "https://acme.github.io/widget/",
    "pages": {"build_type": "workflow"},
    "secrets": "MARKETPLACE_DISPATCH_TOKEN\n",
    "tags": "v0.1.0\n",
}


def fake_gh(state):
    def gh(*args):
        joined = " ".join(args)
        if args[:2] == ("repo", "view"):
            out = json.dumps({"visibility": state["visibility"],
                              "homepageUrl": state["homepageUrl"]})
            return subprocess.CompletedProcess(args, 0, out, "")
        if joined.endswith("/pages"):
            if state["pages"] is None:
                return subprocess.CompletedProcess(args, 1, "", "gh: Not Found (HTTP 404)")
            return subprocess.CompletedProcess(args, 0, json.dumps(state["pages"]), "")
        if args[:2] == ("secret", "list"):
            return subprocess.CompletedProcess(args, 0, state["secrets"], "")
        if "/tags" in joined:
            return subprocess.CompletedProcess(args, 0, state["tags"], "")
        raise AssertionError(f"unexpected gh call: {joined}")
    return gh


@pytest.fixture
def workspace(tmp_path):
    hub = tmp_path / "market"
    hub.mkdir()
    (hub / "plugins.yml").write_text(HUB)
    (hub / "README.md").write_text("### [widget](https://acme.github.io/widget/#/) — tools\n")
    site = tmp_path / "site"
    site.mkdir()
    (site / "projects.yml").write_text(yaml.safe_dump(
        [{"group": "Tools", "children": [{"name": "widget"}]}]))
    plugin = tmp_path / "widget"
    plugin.mkdir()
    (plugin / "plugin.yml").write_text(yaml.safe_dump({
        "name": "widget",
        "description": "Makes widgets.",
        "marketplace": {"category": "development",
                        "homepage": "https://acme.github.io/widget/#/"},
        "suite": {"group": "tools"},
    }))
    return tmp_path


def gaps(workspace, monkeypatch, **state):
    monkeypatch.setattr(onboarding, "gh", fake_gh({**READY, **state}))
    rows = onboarding.checks("widget", workspace / "market")
    return [label for label, ok, _ in rows if not ok]


def test_a_ready_plugin_has_no_gaps(workspace, monkeypatch):
    assert gaps(workspace, monkeypatch) == []


def test_each_github_setting_is_its_own_gap(workspace, monkeypatch):
    found = gaps(workspace, monkeypatch, visibility="PRIVATE", homepageUrl="",
                 pages=None, secrets="", tags="")
    assert found == ["public repo", "repo homepage", "Pages from Actions",
                     "MARKETPLACE_DISPATCH_TOKEN secret", "released"]


def test_an_undeclared_group_is_a_gap(workspace, monkeypatch):
    spec = yaml.safe_load((workspace / "widget" / "plugin.yml").read_text())
    spec["suite"]["group"] = "record"
    (workspace / "widget" / "plugin.yml").write_text(yaml.safe_dump(spec))
    assert gaps(workspace, monkeypatch) == ["suite.group"]


def test_the_aggregator_side_gaps(workspace, monkeypatch):
    manifest = yaml.safe_load(HUB)
    manifest["plugins"] = ["other"]
    (workspace / "market" / "plugins.yml").write_text(yaml.safe_dump(manifest))
    (workspace / "market" / "README.md").write_text("# acme\n")
    (workspace / "site" / "projects.yml").write_text(yaml.safe_dump([{"name": "other"}]))
    assert gaps(workspace, monkeypatch) == ["on plugins.yml", "README section", "hub entry"]


def test_no_hub_declared_means_no_hub_check(workspace, monkeypatch):
    manifest = yaml.safe_load(HUB)
    del manifest["hub"]
    (workspace / "market" / "plugins.yml").write_text(yaml.safe_dump(manifest))
    monkeypatch.setattr(onboarding, "gh", fake_gh(READY))
    labels = [label for label, _, _ in onboarding.checks("widget", workspace / "market")]
    assert "hub entry" not in labels


def test_a_missing_checkout_is_one_gap_naming_the_clone(workspace, monkeypatch):
    monkeypatch.setattr(onboarding, "gh", fake_gh(READY))
    rows = onboarding.checks("gadget", workspace / "market")
    assert [(label, ok) for label, ok, _ in rows] == [("plugin.yml", False)]
    assert "acme/gadget" in rows[0][2]


def test_finds_the_aggregator_from_a_plugin_checkout(workspace):
    assert onboarding.find_aggregator(None, cwd=workspace / "widget") == workspace / "market"


def test_two_aggregators_beside_the_cwd_need_root(workspace):
    other = workspace / "market2"
    other.mkdir()
    (other / "plugins.yml").write_text(HUB)
    with pytest.raises(onboarding.ToolError, match="--root"):
        onboarding.find_aggregator(None, cwd=workspace / "widget")


def test_a_gh_failure_exits_2(workspace, monkeypatch, capsys):
    def broken(*args):
        return subprocess.CompletedProcess(args, 1, "", "HTTP 401: Bad credentials")
    monkeypatch.setattr(onboarding, "gh", broken)
    assert onboarding.run(["widget"], workspace / "market") == 2
    assert "Bad credentials" in capsys.readouterr().err
