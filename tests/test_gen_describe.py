"""Where the derived `describe:` block lands in plugin.yml.

`describe:` is a key of `suite:`, so it has one correct home. The splice used to
find it positionally — replace an existing region, else insert before
`examples:`/`session:`, else append at end-of-file with two-space indent — and
that last fallback is only right while `suite:` is the last top-level key. A
`plugin.yml` with anything after it (a `docs:` block, say) got the block filed
under *that* key instead.

Nothing catches it downstream: the file is valid YAML, `suite.describe` is simply
absent, and the projections that read it come up empty rather than failing. So
these assert placement against the parsed document, not the text.
"""
import textwrap

import pytest
import yaml

from shipyard import gen_describe

BLOCK = gen_describe.render_block({"skills": {"build": "Build the thing."}})


def _splice(text):
    return gen_describe._splice(textwrap.dedent(text).lstrip("\n"), BLOCK)


def _described(text):
    """`suite.describe` as YAML sees it — the question every reader of the file
    actually asks."""
    return (yaml.safe_load(_splice(text)).get("suite") or {}).get("describe")


SUITE_LAST = """
    name: demo
    suite:
      gloss: one line
"""

SUITE_THEN_DOCS = """
    name: demo
    suite:
      gloss: one line
    docs:
      mermaid: true
"""


def test_the_block_lands_under_suite_when_suite_is_last():
    assert _described(SUITE_LAST) == {"skills": {"build": "Build the thing."}}


def test_the_block_lands_under_suite_when_another_key_follows_it():
    """The regression: `docs:` after `suite:` used to collect the block."""
    assert _described(SUITE_THEN_DOCS) == {"skills": {"build": "Build the thing."}}


def test_a_key_after_suite_is_left_alone():
    doc = yaml.safe_load(_splice(SUITE_THEN_DOCS))

    assert doc["docs"] == {"mermaid": True}
    assert "describe" not in doc["docs"]


def test_rerunning_replaces_rather_than_stacking():
    once = _splice(SUITE_THEN_DOCS)
    twice = gen_describe._splice(once, BLOCK)

    assert twice == once
    assert twice.count(gen_describe.BEGIN) == 1


def test_a_block_an_earlier_run_misplaced_is_moved_back():
    """A plugin.yml already carrying the bug's output is repaired by the next
    projection, rather than keeping the misplaced block because the markers
    match wherever they are."""
    misplaced = textwrap.dedent("""
        name: demo
        suite:
          gloss: one line
        docs:
          mermaid: true
        """).lstrip("\n") + BLOCK + "\n"

    doc = yaml.safe_load(gen_describe._splice(misplaced, BLOCK))

    assert doc["suite"]["describe"] == {"skills": {"build": "Build the thing."}}
    assert doc["docs"] == {"mermaid": True}


def test_a_hand_authored_describe_is_replaced_in_place():
    doc = yaml.safe_load(_splice("""
        name: demo
        suite:
          gloss: one line
          describe:
            skills:
              stale: Written by hand, and wrong.
        docs:
          mermaid: true
        """))

    assert doc["suite"]["describe"] == {"skills": {"build": "Build the thing."}}


def test_describe_sorts_ahead_of_session():
    text = _splice("""
        name: demo
        suite:
          gloss: one line
          session:
            - step one
        """)

    assert text.index(gen_describe.BEGIN) < text.index("  session:")


def test_a_plugin_yml_with_no_suite_says_so():
    with pytest.raises(SystemExit, match=r"no `suite:` block"):
        _splice("""
            name: demo
            docs:
              mermaid: true
            """)


def test_an_inline_suite_says_so_rather_than_writing_unparseable_yaml():
    """`suite: {sessions: []}` has no block body. Indenting `describe:` under a
    flow mapping isn't nesting, it's a parse error — so the old end-of-file
    append left a plugin.yml that no longer loaded, and nothing re-read it to
    notice."""
    with pytest.raises(SystemExit, match=r"writes `suite:` inline"):
        _splice("""
            name: demo
            suite: {sessions: []}
            """)


def test_every_spliced_result_still_parses():
    """The property the failure violated, asserted directly."""
    for text in (SUITE_LAST, SUITE_THEN_DOCS):
        assert yaml.safe_load(_splice(text))
