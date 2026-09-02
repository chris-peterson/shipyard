"""The interop event catalog: a plugin's own events page, and the suite-level
aggregation that pairs publishers with subscribers.

The two halves are asymmetric on purpose. A producer declares an event in full
because it emits the fields; a consumer declares only the key it depends on,
because N consumers restating one schema is N copies to drift.

What the aggregation is *for* is the orphan cases. A subscriber that never
matches looks exactly like an event that never fired, so a key with only one end
is the failure this data exists to surface, and most of the tests below are
about that rather than about the happy pairing.
"""
import json
import textwrap

import pytest
import yaml

from shipyard import build_docs, gen_events_json

HUB = textwrap.dedent("""\
    name: chris-peterson
    description: Chris Peterson's Claude Code plugins
    owner: chris-peterson
    source: https://github.com/{owner}/{name}.git
    plugins:
      - anchor
      - tack
""")

PUBLISHER = {
    "name": "anchor",
    "version": "1.12.0",
    "description": "Consistency across the code-change lifecycle.",
    "events": {
        "publishes": [
            {
                "key": "cr.created",
                "when": "prepare-review opened a change request.",
                "emitted_by": "scripts/prepare-review.sh",
                "fields": {
                    "uri": "the change request's web address",
                    "title": {
                        "describe": "its title, as the forge reports it",
                        "optional": True,
                    },
                },
            },
        ],
    },
}

SUBSCRIBER = {
    "name": "tack",
    "version": "1.6.0",
    "description": "Track AI-assisted development work.",
    "events": {
        "subscribes": [
            {
                "key": "codes.bridgeai.anchor/cr.created",
                "handled_by": "hooks/capture-urls.sh",
                "reason": "records the change request on the session's route",
            },
        ],
    },
}


@pytest.fixture
def hub(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    (root / "plugins.yml").write_text(HUB)
    return root


def write_spokes(hub, *specs):
    for spec in specs:
        d = hub.parent / spec["name"]
        d.mkdir(exist_ok=True)
        (d / "plugin.yml").write_text(yaml.safe_dump(spec, sort_keys=False))


def catalog(hub):
    return json.loads(gen_events_json.build(hub))


# --- the pairing ------------------------------------------------------------

def test_a_subscriber_lands_on_the_publisher_entry(hub):
    write_spokes(hub, PUBLISHER, SUBSCRIBER)
    data = catalog(hub)
    assert [e["key"] for e in data["events"]] == ["codes.bridgeai.anchor/cr.created"]
    assert data["events"][0]["subscribers"] == [{
        "subscriber": "tack",
        "handled_by": "hooks/capture-urls.sh",
        "reason": "records the change request on the session's route",
    }]


def test_the_publisher_supplies_its_own_prefix(hub):
    # A producer declares a bare key, so it cannot typo its own namespace.
    write_spokes(hub, PUBLISHER, SUBSCRIBER)
    assert catalog(hub)["events"][0]["publisher"] == "anchor"
    assert catalog(hub)["events"][0]["key"].startswith("codes.bridgeai.anchor/")


def test_a_paired_key_is_in_neither_orphan_list(hub):
    write_spokes(hub, PUBLISHER, SUBSCRIBER)
    data = catalog(hub)
    assert data["published_only"] == []
    assert data["subscribed_only"] == []


def test_several_subscribers_to_one_key_are_all_listed(hub):
    beacon = {**SUBSCRIBER, "name": "beacon"}
    (hub / "plugins.yml").write_text(HUB + "  - beacon\n")
    write_spokes(hub, PUBLISHER, SUBSCRIBER, beacon)
    subs = catalog(hub)["events"][0]["subscribers"]
    assert [s["subscriber"] for s in subs] == ["beacon", "tack"]


# --- the orphans, which are the point ---------------------------------------

def test_a_published_key_nobody_hears_is_reported(hub):
    write_spokes(hub, PUBLISHER, {**SUBSCRIBER, "events": {}})
    data = catalog(hub)
    assert data["published_only"] == ["codes.bridgeai.anchor/cr.created"]
    assert data["subscribed_only"] == []


def test_a_subscription_to_nothing_is_reported(hub):
    # Always a defect: a typo, or a key whose publisher was renamed out from
    # under it. The publisher-only case is usually just a rollout mid-flight.
    write_spokes(hub, {**PUBLISHER, "events": {}}, SUBSCRIBER)
    data = catalog(hub)
    assert data["events"] == []
    assert data["subscribed_only"] == [{
        "key": "codes.bridgeai.anchor/cr.created",
        "subscriber": "tack",
        "handled_by": "hooks/capture-urls.sh",
        "reason": "records the change request on the session's route",
    }]


def test_a_subscriber_naming_a_stale_key_does_not_pair(hub):
    stale = {**SUBSCRIBER, "events": {"subscribes": [
        {"key": "codes.bridgeai.anchor/cr.opened", "handled_by": "x.sh"}]}}
    write_spokes(hub, PUBLISHER, stale)
    data = catalog(hub)
    assert data["events"][0]["subscribers"] == []
    assert [s["key"] for s in data["subscribed_only"]] == ["codes.bridgeai.anchor/cr.opened"]


def test_a_plugin_declaring_no_events_is_simply_absent(hub):
    write_spokes(hub, {k: v for k, v in PUBLISHER.items() if k != "events"},
                 {k: v for k, v in SUBSCRIBER.items() if k != "events"})
    data = catalog(hub)
    assert data == {"events": [], "subscribed_only": [], "published_only": []}


# --- field declarations -----------------------------------------------------

def test_a_string_field_is_shorthand_for_a_required_string(hub):
    write_spokes(hub, PUBLISHER, SUBSCRIBER)
    uri = catalog(hub)["events"][0]["fields"][0]
    assert uri == {
        "name": "uri",
        "type": "string",
        "optional": False,
        "describe": "the change request's web address",
    }


def test_the_expanded_form_carries_optionality(hub):
    write_spokes(hub, PUBLISHER, SUBSCRIBER)
    title = catalog(hub)["events"][0]["fields"][1]
    assert title["optional"] is True
    assert title["describe"] == "its title, as the forge reports it"


# --- the rendered page ------------------------------------------------------

def test_the_page_anchors_each_event_explicitly():
    # A dotted heading does not slugify to anything a reader would guess:
    # docsify strips punctuation rather than converting it.
    page = build_docs._render_events_md(PUBLISHER)
    assert "## `cr.created` :id=cr-created" in page


def test_the_page_shows_the_fully_qualified_key():
    page = build_docs._render_events_md(PUBLISHER)
    assert "codes.bridgeai.anchor/cr.created" in page


def test_an_optional_field_is_not_advertised_as_always_set():
    page = build_docs._render_events_md(PUBLISHER)
    assert "| `title` | may be empty |" in page
    assert "| `uri` | always set |" in page


def test_the_callouts_are_single_blockquotes():
    # A blank line between the marker and the body ends the quote, and the page
    # renders a literal "[!NOTE]" above an unrelated one.
    page = build_docs._render_events_md(PUBLISHER)
    assert "> [!NOTE]\n> " in page
    assert "> [!WARNING]\n> " in page
    assert "> [!NOTE]\n\n" not in page


def test_a_single_event_gets_no_index_list():
    page = build_docs._render_events_md(PUBLISHER)
    assert "each linkable on its own" not in page


def test_several_events_get_an_index_list():
    spec = {**PUBLISHER, "events": {"publishes": [
        *PUBLISHER["events"]["publishes"],
        {"key": "cr.updated", "when": "it changed one.", "fields": {"uri": "where"}},
    ]}}
    page = build_docs._render_events_md(spec)
    assert "- [`cr.created`](#cr-created)" in page
    assert "- [`cr.updated`](#cr-updated)" in page


def test_emitted_by_is_code_for_a_path_and_prose_otherwise():
    page = build_docs._render_events_md(PUBLISHER)
    assert "Emitted by `scripts/prepare-review.sh`." in page

    spec = {**PUBLISHER, "events": {"publishes": [
        {**PUBLISHER["events"]["publishes"][0],
         "emitted_by": "skills/prepare-review, via scripts/announce.sh"},
    ]}}
    prose = build_docs._render_events_md(spec)
    assert "Emitted by skills/prepare-review, via scripts/announce.sh." in prose
