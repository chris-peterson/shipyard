"""The relevance projection: a plugin's `marketplace.relevance:` → its marketplace entry.

Claude Code reads this block and never reports on it. A signal name it doesn't
recognize is ignored at load time, so the plugin quietly makes none of the
suggestions its owner wrote it for — which is why the shapes below are errors
here rather than something to notice later.
"""
import json
import textwrap

import pytest
import yaml

from shipyard import _validate, gen_marketplace_json

HUB = textwrap.dedent("""\
    name: chris-peterson
    description: Chris Peterson's Claude Code plugins
    owner: chris-peterson
    source: https://github.com/{owner}/{name}.git
    plugins:
      - anchor
""")

WELL_FORMED = {
    "topic": "Terraform",
    "signals": {
        "cwd": ["infra/**"],
        "cli": ["terraform"],
        "hosts": ["registry.terraform.io"],
        "filesRead": ["**/*.tf"],
        "manifestDeps": [{"file": r"[/\\]package\.json$", "pattern": r'"stripe"\s*:'}],
    },
}


@pytest.fixture
def hub(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    (root / "plugins.yml").write_text(HUB)
    (tmp_path / "anchor").mkdir()
    return root


def write_spoke(hub, relevance=None, **extra):
    spec = {
        "name": "anchor",
        "version": "1.3.0",
        "description": "Consistency across the code-change lifecycle.",
        "author": "chris-peterson",
        "marketplace": {"category": "development"},
    }
    if relevance is not None:
        spec["marketplace"]["relevance"] = relevance
    spec.update(extra)
    (hub.parent / "anchor" / "plugin.yml").write_text(yaml.safe_dump(spec))


def entry(hub):
    return json.loads(gen_marketplace_json.build(hub))["plugins"][0]


def rejects(relevance, expected):
    errors = _validate.relevance_errors(relevance)
    assert any(expected in e for e in errors), \
        f"expected an error mentioning {expected!r}, got: {errors}"


# ---- the projection ---------------------------------------------------------

def test_a_well_formed_block_reaches_the_marketplace_entry(hub):
    write_spoke(hub, WELL_FORMED)
    assert entry(hub)["relevance"] == WELL_FORMED


def test_relevance_lands_after_the_entry_s_own_fields(hub):
    """Field order is part of a committed artifact, so pin where it goes."""
    write_spoke(hub, {"signals": {"cli": ["terraform"]}})
    assert list(entry(hub)) == ["name", "description", "author", "source",
                                "category", "relevance"]


def test_a_plugin_declaring_none_publishes_without_the_field(hub):
    write_spoke(hub)
    assert "relevance" not in entry(hub)


def test_topic_is_optional(hub):
    write_spoke(hub, {"signals": {"cli": ["terraform"]}})
    assert entry(hub)["relevance"] == {"signals": {"cli": ["terraform"]}}


def test_a_bad_block_names_the_plugin_and_the_field(hub):
    write_spoke(hub, {"signals": {"filesread": ["**/*.tf"]}})
    with pytest.raises(SystemExit, match=r"(?s)anchor/plugin.yml.*filesread"):
        gen_marketplace_json.build(hub)


# ---- what Claude Code loads and then ignores --------------------------------

def test_a_misspelled_signal_is_rejected_rather_than_ignored():
    rejects({"signals": {"filesread": ["**/*.tf"]}}, "filesread is not a signal")


def test_a_misspelled_signal_beside_a_valid_one_is_still_rejected():
    """The case with no other symptom: the block matches on `cli` and the owner
    never learns the second signal was dropped."""
    rejects({"signals": {"cli": ["terraform"], "filesread": ["**/*.tf"]}},
            "filesread is not a signal")


def test_an_unknown_key_under_relevance_is_rejected():
    rejects({"topcic": "T", "signals": {"cli": ["terraform"]}},
            "topcic is not a relevance field")


def test_a_relevance_block_that_is_not_a_mapping_is_rejected():
    rejects("terraform", "must be a mapping")


def test_a_block_with_no_signals_is_rejected():
    rejects({"topic": "Terraform"}, "/relevance/signals is required")


def test_an_empty_signals_mapping_is_rejected():
    rejects({"signals": {}}, "declares no signal")


def test_an_empty_signal_list_is_rejected():
    rejects({"signals": {"cli": []}}, "/relevance/signals/cli is empty")


def test_a_signal_that_is_not_a_list_is_rejected():
    rejects({"signals": {"cli": "terraform"}}, "must be a list")


# ---- the caps ---------------------------------------------------------------

def test_a_topic_over_64_characters_is_rejected():
    rejects({"topic": "x" * 65, "signals": {"cli": ["t"]}}, "longer than 64")


def test_a_signal_over_its_entry_cap_is_rejected():
    rejects({"signals": {"cli": [f"c{i}" for i in range(11)]}}, "over the cap of 10")


def test_hosts_has_its_own_higher_cap():
    assert _validate.relevance_errors(
        {"signals": {"hosts": [f"h{i}.example.com" for i in range(20)]}}) == []
    rejects({"signals": {"hosts": [f"h{i}.example.com" for i in range(21)]}},
            "over the cap of 20")


def test_an_over_long_entry_is_rejected():
    rejects({"signals": {"cwd": ["x" * 257]}}, "longer than 256 characters")


def test_a_repeated_pattern_is_rejected():
    """Claude Code accepts it; it spends one of ten slots on nothing."""
    rejects({"signals": {"cwd": ["infra/**", "infra/**"]}}, "more than once")


# ---- hosts ------------------------------------------------------------------

@pytest.mark.parametrize("host", [
    "https://api.stripe.com", "api.stripe.com:443", "api.stripe.com/v1",
    "API.Stripe.com",
])
def test_a_host_that_is_not_a_bare_lowercase_hostname_is_rejected(host):
    rejects({"signals": {"hosts": [host]}}, "bare lowercase hostname")


def test_a_bare_hostname_is_accepted():
    assert _validate.relevance_errors({"signals": {"hosts": ["api.stripe.com"]}}) == []


# ---- manifestDeps -----------------------------------------------------------

def test_an_uncompilable_regex_is_rejected():
    rejects({"signals": {"manifestDeps": [{"file": r"package\.json$",
                                           "pattern": "([unclosed"}]}},
            "manifestDeps/0/pattern is not a valid regular expression")


def test_a_manifest_dep_missing_a_field_is_rejected():
    rejects({"signals": {"manifestDeps": [{"file": r"package\.json$"}]}},
            "manifestDeps/0/pattern must be a non-empty string")


def test_an_unknown_manifest_dep_field_is_rejected():
    rejects({"signals": {"manifestDeps": [{"file": r"x$", "pattern": "y",
                                           "contents": "z"}]}},
            "manifestDeps/0/contents is not a manifestDeps field")


def test_the_documented_manifest_dep_shape_is_accepted():
    assert _validate.relevance_errors(WELL_FORMED) == []
