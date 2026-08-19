"""Where shipyard's own CI surface refers back to shipyard.

A reusable workflow can't read the ref its caller pinned it at — `uses:` takes no
expression — so each self-reference hardcodes one. That's correct only while every
self-reference on a line names *that* line: the copy at the `v1` tag has to say
`v1`, the copy on the `v2` line has to say `v2`.

Two live majors are what make a mismatch reachable. A caller at `@v2` whose
workflow reaches a `@v1` self-reference runs the other line's code, and nothing
about the run says so: `deploy-docs.yml` would build its docs with v1's renderer,
and `release.yml` would run v1's generators over the plugin's sources. Both fail
in the caller's repo, quietly, and only for the majors that disagree.
"""
import pathlib

import yaml

ROOT = pathlib.Path(__file__).parents[1]
SELF = "chris-peterson/shipyard"

SURFACE = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + \
          sorted((ROOT / "actions").glob("*/action.yml"))


def _steps(doc):
    """Every step in a workflow or a composite action, however it's nested."""
    for job in (doc.get("jobs") or {}).values():
        yield from (job.get("steps") or [])
    yield from ((doc.get("runs") or {}).get("steps") or [])


def _self_references(path):
    """(where, ref) for each place this file names shipyard itself.

    Two spellings reach the same thing: `uses:` on an action in this repo, and an
    `actions/checkout` of this repo by `repository:` + `ref:`.
    """
    doc = yaml.safe_load(path.read_text()) or {}
    for step in _steps(doc):
        uses = step.get("uses") or ""
        if uses.startswith(f"{SELF}/") and "@" in uses:
            path_part, ref = uses.rsplit("@", 1)
            yield f"{path.name}: uses {path_part}", ref
        with_ = step.get("with") or {}
        if with_.get("repository") == SELF and with_.get("ref"):
            yield f"{path.name}: checkout {SELF}", str(with_["ref"])


def test_the_self_references_are_found():
    """A rename that hides a self-reference from this module would make the test
    below vacuous, so assert the set rather than trusting it to be non-empty."""
    found = {where for path in SURFACE for where, _ in _self_references(path)}
    assert found == {
        "deploy-docs.yml: uses chris-peterson/shipyard/actions/build-docs",
        "release.yml: checkout chris-peterson/shipyard",
    }


def test_every_self_reference_pins_this_line():
    refs = {where: ref for path in SURFACE for where, ref in _self_references(path)}
    assert len(set(refs.values())) == 1, \
        "self-references disagree on the major: " + \
        "; ".join(f"{where} -> {ref}" for where, ref in sorted(refs.items()))
