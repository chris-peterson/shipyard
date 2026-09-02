"""The growth view's projection: the artifact log plus the spokes' releases →
docs/artifacts.json.

The release half reads real git tags out of real checkouts, because "a release is
a tag plus the changelog section it published" is the contract, not an
implementation detail. The teaser half is pure, and tested against the shapes the
suite's own changelogs actually take.
"""
import json
import subprocess
import textwrap

import pytest
import yaml

from shipyard import _aggregate, changelog, gen_artifacts_json

HUB = textwrap.dedent("""\
    name: chris-peterson
    description: Chris Peterson's Claude Code plugins
    owner: chris-peterson
    source: https://github.com/{owner}/{name}.git
    plugins:
      - guard
      - keeper
    artifacts: log/artifacts.csv
    groups:
      - key: safety
        accent: --guard
        tag: Stay safe
      - key: record
        accent: --build
        tag: Write it down
        retired:
          - ledger
""")

LOG = textwrap.dedent("""\
    date,at,plugin,skills,rules,hooks,commands,agents,change
    2026-01-13,,guard,2,0,0,0,0,+skill:one +skill:two
    2026-01-20,,keeper,1,0,0,0,0,+skill:keep
    2026-01-27,,guard,3,0,0,0,0,+skill:three
    2026-02-03,,ledger,1,0,0,0,0,+skill:note
    2026-02-10,,ledger,0,0,0,0,0,-plugin:ledger
""")

CHANGELOG = textwrap.dedent("""\
    # Changelog

    ## 0.2.0

    ### Changed

    - **The guard names the rule it fired on.** It used to print the file alone.
    - A second change with no lead-in. It has a following sentence.

    ## 0.1.0

    ### Added

    - **First release.** Everything.
""")


def _git(root, *args):
    subprocess.run(("git", "-C", str(root), *args), check=True,
                   capture_output=True, text=True)


def _spoke(workspace, name, group, changelog_text=CHANGELOG, tags=("v0.1.0", "v0.2.0")):
    root = workspace / name
    root.mkdir()
    (root / "plugin.yml").write_text(yaml.safe_dump({
        "name": name,
        "version": "0.2.0",
        "description": f"The {name} plugin.",
        "suite": {"group": group, "pitch": "a pitch"},
    }))
    (root / "CHANGELOG.md").write_text(changelog_text)
    _git(root, "init", "--quiet", "--initial-branch=main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", "Initial")
    for tag in tags:
        _git(root, "tag", tag)
    return root


@pytest.fixture
def hub(tmp_path):
    """An aggregator with a log, two rostered spokes, and one retired beside it."""
    root = tmp_path / "hub"
    (root / "log").mkdir(parents=True)
    (root / "plugins.yml").write_text(HUB)
    (root / "log" / "artifacts.csv").write_text(LOG)
    _spoke(tmp_path, "guard", "safety")
    _spoke(tmp_path, "keeper", "record")
    _spoke(tmp_path, "ledger", "record", tags=("v0.1.0",))
    return root


class TestGroups:
    def test_catalog_order_places_the_roster_then_the_retired(self, hub):
        # a plugin off the roster keeps the group and the slot it held, so its
        # band stays where it was in every week it existed
        assert _aggregate.grouped(hub) == [
            ("guard", "safety", 0),
            ("keeper", "record", 0),
            ("ledger", "record", 1),
        ]

    def test_a_group_no_entry_declares_is_an_error(self, hub, tmp_path):
        spec = yaml.safe_load((tmp_path / "guard" / "plugin.yml").read_text())
        spec["suite"]["group"] = "bearings"
        (tmp_path / "guard" / "plugin.yml").write_text(yaml.safe_dump(spec))
        with pytest.raises(SystemExit) as exc:
            _aggregate.grouped(hub)
        assert "bearings" in str(exc.value)

    def test_a_spoke_with_no_group_is_an_error(self, hub, tmp_path):
        spec = yaml.safe_load((tmp_path / "guard" / "plugin.yml").read_text())
        del spec["suite"]["group"]
        (tmp_path / "guard" / "plugin.yml").write_text(yaml.safe_dump(spec))
        with pytest.raises(SystemExit) as exc:
            _aggregate.grouped(hub)
        assert "suite.group" in str(exc.value)

    def test_retired_urls_resolve_through_the_roster_template(self, hub):
        # the sync step has to clone them, and they have no roster entry to
        # carry a URL of their own
        assert _aggregate.retired(hub) == [
            ("ledger", "https://github.com/chris-peterson/ledger.git")]


class TestCatalogData:
    def test_groups_ride_alongside_the_plugins(self, hub):
        from shipyard import gen_plugins_js
        text = gen_plugins_js.build(hub)
        assert '"key": "safety"' in text
        assert '"accent": "--guard"' in text
        # membership stays with the plugins, so the array carries no name list
        assert "ledger" not in text.split("const GROUPS")[1]

    def test_a_cli_plugin_is_marked_as_having_a_reference(self, hub, tmp_path):
        from shipyard import gen_plugins_js
        spec = yaml.safe_load((tmp_path / "guard" / "plugin.yml").read_text())
        spec["cli"] = {"name": "guard", "engine": "argparse"}
        (tmp_path / "guard" / "plugin.yml").write_text(yaml.safe_dump(spec))
        from test_aggregate import plugins_of
        data = plugins_of(gen_plugins_js.build(hub))
        assert data["guard"]["reference"] is True
        assert "reference" not in data["keeper"]


class TestSeries:
    def test_a_plugin_has_no_band_before_its_first_change_point(self, hub):
        rows = gen_artifacts_json.log_rows(hub)
        buckets = gen_artifacts_json.week_buckets("2026-01-13")
        series = gen_artifacts_json.build_series(rows, ["keeper"], buckets)
        # keeper's first change point is 2026-01-20, the second bucket
        assert series["keeper"][0] is None
        assert series["keeper"][1] == 1

    def test_a_total_forward_fills_through_quiet_weeks(self, hub):
        rows = gen_artifacts_json.log_rows(hub)
        buckets = gen_artifacts_json.week_buckets("2026-01-13")
        guard = gen_artifacts_json.build_series(rows, ["guard"], buckets)["guard"]
        assert guard[0] == 2          # 2026-01-13
        assert guard[1] == 2          # quiet week, held
        assert guard[2] == 3          # 2026-01-27
        assert guard[3] == 3          # quiet week, held


class TestReleases:
    def test_a_release_carries_its_tag_instant_and_teaser(self, hub):
        rels = gen_artifacts_json.spoke_releases("guard", hub)
        assert [r["tag"] for r in rels] == ["v0.1.0", "v0.2.0"]
        assert rels[1]["summary"]["buckets"][0]["title"] == "Changed"
        assert rels[0]["published_at"]  # an instant, not a calendar day

    def test_a_tag_with_no_section_is_a_release_with_no_teaser(self, tmp_path, hub):
        _spoke(tmp_path, "extra", "safety", tags=("v0.1.0", "v0.9.9"))
        rels = gen_artifacts_json.spoke_releases("extra", hub)
        ninth = next(r for r in rels if r["tag"] == "v0.9.9")
        assert ninth["summary"] == {}

    def test_a_release_links_the_page_its_tag_published(self, hub):
        # the projection makes no forge call, so the link is resolved through
        # the same source: template the roster is
        rels = gen_artifacts_json.spoke_releases("guard", hub)
        assert rels[1]["url"] == \
            "https://github.com/chris-peterson/guard/releases/tag/v0.2.0"

    def test_a_retirement_claims_the_last_version_it_shipped(self, hub):
        rows = gen_artifacts_json.log_rows(hub)
        releases = {p: gen_artifacts_json.spoke_releases(p, hub)
                    for p in ("guard", "keeper", "ledger")}
        entries, claimed = gen_artifacts_json.build_changelog(rows, releases)
        retirement = next(e for e in entries if e.get("removed"))
        assert retirement["last_release"]["tag"] == "v0.1.0"
        # the retirement line links it too — a retired plugin's repo is where
        # the version anyone still has installed is published from
        assert retirement["last_release"]["url"] == \
            "https://github.com/chris-peterson/ledger/releases/tag/v0.1.0"
        # reported on the retirement line alone, so it opens no entry of its own
        listed = gen_artifacts_json.build_releases(["ledger"], releases, claimed)
        assert listed == []


class TestProjection:
    def test_the_projection_covers_every_logged_plugin_in_catalog_order(self, hub):
        data = gen_artifacts_json.build(hub)
        assert data["plugins"] == ["guard", "keeper", "ledger"]
        # a band resolves its color through the group, which is what lets a
        # retired plugin keep one with no catalog card left to read it from
        assert data["colors"]["ledger"] == {"group": "record", "shade": 1}

    def test_run_writes_the_render_target(self, hub):
        assert gen_artifacts_json.run(hub) == 0
        data = json.loads((hub / "docs" / "artifacts.json").read_text())
        assert data["dates"][0] == "2026-01-12"  # the Monday of the first week

    def test_an_aggregator_with_no_log_declares_nothing_to_project(self, hub):
        manifest = yaml.safe_load((hub / "plugins.yml").read_text())
        del manifest["artifacts"]
        (hub / "plugins.yml").write_text(yaml.safe_dump(manifest))
        with pytest.raises(SystemExit) as exc:
            gen_artifacts_json.build(hub)
        assert "artifacts:" in str(exc.value)


class TestTeaser:
    BODY = textwrap.dedent("""\
        > [!WARNING]
        > **One-time setup — name the review tool you want.** Which tool a review
        > opens is now yours to set:
        >
        > ```bash
        > git config --global anchor.edit.tool hx
        > ```

        ### Changed

        - **Diff reviews open wherever editor reviews already did.** A review that
          needs a terminal takes the first host it can reach.
        - A review reports whether it can open by asking both halves. It used to
          say otherwise.
        - **Third.** x
        - **Fourth.** y

        ### Fixed

        - **A review with nothing to edit points at the flag that fixes it.** It
          names `--mode diff` now.
    """)

    def test_the_alert_leads_with_its_own_headline(self):
        # the `[!WARNING]` marker and the fenced command are structure; what a
        # reader needs is the sentence the alert opens with
        assert changelog.teaser(self.BODY)["alert"] == \
            "One-time setup — name the review tool you want"

    def test_each_bucket_keeps_a_capped_set_of_headlines(self):
        sm = changelog.teaser(self.BODY)
        assert [b["title"] for b in sm["buckets"]] == ["Changed", "Fixed"]
        changed = sm["buckets"][0]
        assert changed["items"][0] == \
            "Diff reviews open wherever editor reviews already did"
        # no bold lead-in, so the first sentence stands in
        assert changed["items"][1] == \
            "A review reports whether it can open by asking both halves"
        assert changed["more"] == 1
        assert "more" not in sm["buckets"][1]

    def test_buckets_are_capped_too(self):
        body = "".join(f"### S{i}\n\n- **Lead {i}.** x\n\n" for i in range(9))
        sm = changelog.teaser(body)
        assert len(sm["buckets"]) == changelog.TEASER_BUCKETS
        assert sm["more"] == 9 - changelog.TEASER_BUCKETS

    def test_a_long_headline_is_clipped_without_a_dangling_space(self):
        sm = changelog.teaser("- " + "word " * 40)
        (item,) = sm["buckets"][0]["items"]
        assert len(item) <= changelog.TEASER_CHARS
        assert item.endswith("…")
        assert not item.endswith(" …")

    def test_an_identifiers_underscores_survive(self):
        # sweeping ``[`*_]+`` as one class turned `created_at` into `createdat`,
        # which names nothing a reader could search the repo for
        sm = changelog.teaser(
            "- A route's `created_at` can no longer postdate _its own_ work.\n")
        assert sm["buckets"][0]["items"] == \
            ["A route's created_at can no longer postdate its own work"]

    def test_a_bucket_with_no_bullets_falls_back_to_its_paragraph(self):
        # some sections are a heading naming the change and prose explaining it
        sm = changelog.teaser(
            "### `serve` refuses an opaque origin\n\n"
            "2.9.0's origin gate read a literal `Origin: null` as a missing header.\n")
        (bucket,) = sm["buckets"]
        assert bucket["title"] == "serve refuses an opaque origin"
        assert bucket["items"] == \
            ["2.9.0's origin gate read a literal Origin: null as a missing header"]

    def test_bullets_win_over_the_paragraph_introducing_them(self):
        sm = changelog.teaser("### Changed\n\nThese landed:\n\n- **One.** x\n")
        assert sm["buckets"][0]["items"] == ["One"]

    def test_an_empty_body_teases_nothing(self):
        # which is how a consumer knows to render no card for that release
        assert changelog.teaser("") == {}


class TestSectionBoundary:
    def test_a_section_bucketed_with_h2_still_reads(self, tmp_path):
        # sections written before the `###` skeleton bucket with `## Fixed`, and
        # reading that as a version boundary makes the notes above it vanish
        (tmp_path / "CHANGELOG.md").write_text(textwrap.dedent("""\
            # Changelog

            ## 1.0.1

            ## Fixed

            - **A real fix.** With prose.

            ## 1.0.0

            - First.
        """))
        body = changelog.released_body("1.0.1", tmp_path)
        assert "A real fix" in body
        assert "1.0.0" not in body
        assert changelog.teaser(body)["buckets"][0]["title"] == "Fixed"

    def test_a_missing_version_reads_as_absent_rather_than_empty(self, tmp_path):
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- One.\n")
        assert changelog.released_body("9.9.9", tmp_path) is None
