import pytest

from shipyard import links

# What a plugin publishes, as the rewrite sees it: source path -> site route.
ROUTES = {
    "skills/spec-req/SKILL.md": "/skills/spec-req",
    "skills/spec-sync/SKILL.md": "/skills/spec-sync",
    "skills/note/references/hand-edit-mode.md": "/skills/note/references/hand-edit-mode",
    "references/locate-spec.md": "/references/locate-spec",
    "SPEC.md": "/spec",
    "STATUS.md": "/status",
}


def rewrite(text, source="skills/spec-req/SKILL.md"):
    return links.rewrite(text, source, ROUTES)


def test_a_link_written_for_the_checkout_becomes_the_route_it_is_served_at():
    """The 404 this whole mechanism exists for: `../../references/locate-spec.md`
    is right in the checkout and one level too deep for the published page."""
    assert rewrite("see [locate](../../references/locate-spec.md)") == (
        "see [locate](/references/locate-spec)")


def test_a_cross_skill_link_lands_on_the_other_skills_page():
    assert rewrite("see [sync](../spec-sync/SKILL.md)") == "see [sync](/skills/spec-sync)"


def test_a_skills_own_references_keep_their_place_under_it():
    assert links.rewrite("see [mode](references/hand-edit-mode.md)",
                         "skills/note/SKILL.md", ROUTES) == (
        "see [mode](/skills/note/references/hand-edit-mode)")


def test_the_ledgers_link_to_the_spec_follows_the_lowercased_route():
    assert links.rewrite("declared in [`SPEC.md`](SPEC.md).", "STATUS.md", ROUTES) == (
        "declared in [`SPEC.md`](/spec).")


def test_a_fragment_survives_as_the_deep_link_docsify_understands():
    assert rewrite("see [x](../../references/locate-spec.md#the-shape)") == (
        "see [x](/references/locate-spec?id=the-shape)")


def test_a_link_to_something_unpublished_is_left_exactly_as_written():
    """Rewriting it to a guess would bury a real dead end under a plausible
    route; the check reports it instead."""
    text = "see [changes](../../CHANGELOG.md)"

    assert rewrite(text) == text


def test_a_link_inside_a_fence_is_an_example_not_a_link():
    text = "```markdown\n[locate](../../references/locate-spec.md)\n```\n"

    assert rewrite(text) == text


def test_a_link_quoted_in_a_double_backtick_span_is_prose():
    """``[`SPEC.md`](SPEC.md)`` is a guide showing the reader a link. A
    single-backtick pattern tears the span in half and rewrites the wreckage."""
    text = "Write ``declared in [`SPEC.md`](SPEC.md)`` at the top."

    assert links.rewrite(text, "STATUS.md", ROUTES) == text


def test_two_links_on_one_line_both_move():
    assert rewrite("[a](../../references/locate-spec.md) and [b](../spec-sync/SKILL.md)") == (
        "[a](/references/locate-spec) and [b](/skills/spec-sync)")


def test_an_absolute_link_is_already_a_route():
    text = "see [home](/) and [sync](/skills/spec-sync)"

    assert rewrite(text) == text


@pytest.mark.parametrize("heading, slug", [
    ("`LOCATE-01`", "locate-01"),
    ("LOCATE-01", "locate-01"),
    ("`LOCATE`", "locate"),
    ("The shape", "the-shape"),
    ("Why headings?", "why-headings"),
    ("[Spec layout](spec-layout.md)", "spec-layout"),
    ("Step 1: locate", "step-1-locate"),
    ("under_scores kept", "under_scores-kept"),
])
def test_the_slug_docsify_gives_a_heading(heading, slug):
    """The backticked form is the one that matters here: sextant heads every
    requirement with `` `XX-NN` ``, and `SPEC.md#locate-01` has to keep resolving."""
    assert links.slugify(heading) == slug


def test_a_heading_that_repeats_takes_the_suffix_docsify_appends():
    assert links.anchors("## Notes\n\n## Notes\n") == {"notes", "notes-1"}


def test_an_explicit_id_is_an_anchor_too():
    assert "manual" in links.anchors('<a id="manual"></a>\n\n# Page\n')


def test_a_heading_inside_a_fence_is_not_an_anchor():
    assert links.anchors("```\n# Not a heading\n```\n") == set()


def test_a_route_resolves_to_the_page_docsify_fetches(tmp_path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "spec-req.md").write_text("# spec-req\n")

    assert links.page_for(tmp_path, "/skills/spec-req").name == "spec-req.md"
    assert links.page_for(tmp_path, "skills/spec-req.md").name == "spec-req.md"
    assert links.page_for(tmp_path, "/skills/nope") is None


def test_a_route_whose_case_does_not_match_the_file_resolves_nowhere(tmp_path):
    """The reported bug, and the one class of dead link that can't be reproduced
    on a Mac: GitHub Pages is case-sensitive, the author's filesystem isn't."""
    (tmp_path / "spec.md").write_text("# spec\n")

    assert links.page_for(tmp_path, "/spec") is not None
    assert links.page_for(tmp_path, "/SPEC") is None


def test_a_route_climbing_out_of_the_tree_resolves_nowhere(tmp_path):
    """`#/../../references/x` is what an unrewritten source link becomes, and
    docsify answers it with its 404 page — so must this."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "x.md").write_text("# x\n")

    assert links.page_for(tmp_path / "docs", "../../references/x") is None
