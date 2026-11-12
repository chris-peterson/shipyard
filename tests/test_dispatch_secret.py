"""`shipyard dispatch-secret`: the marketplace dispatch token, fanned out to the plugins.

The token is a credential, so these hold the two things that matter about it:
it never appears in an argument list, and nothing is written unless it passed
both checks first. `gh` and git are replaced with a recorder.
"""
import subprocess
import textwrap

import pytest

from shipyard import dispatch_secret

TOKEN = "github_pat_example"

HUB = textwrap.dedent("""\
    name: acme
    owner: acme
    source: https://github.com/{owner}/{name}.git
    plugins:
      - widget
      - gadget
""")


@pytest.fixture
def market(tmp_path):
    root = tmp_path / "market"
    root.mkdir()
    (root / "plugins.yml").write_text(HUB)
    return root


@pytest.fixture
def gh(monkeypatch):
    calls = []
    state = {"auth": True, "dispatch": True}

    def run(args, *, token=None, stdin=None):
        calls.append({"args": args, "token": token, "stdin": stdin})
        if args[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(args, 0, "git@github.com:acme/market.git\n", "")
        if args[:3] == ["gh", "api", "user"]:
            if not state["auth"]:
                return subprocess.CompletedProcess(args, 1, "", "HTTP 401: Bad credentials")
            return subprocess.CompletedProcess(args, 0, "someone\n", "")
        if "dispatches" in args[2]:
            ok = state["dispatch"]
            return subprocess.CompletedProcess(args, 0 if ok else 1, "", "" if ok else "HTTP 403")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dispatch_secret, "run", run)
    monkeypatch.setenv("MARKETPLACE_DISPATCH_TOKEN", f"  {TOKEN}\n")
    return calls, state


def writes(calls):
    return [c for c in calls if c["args"][:3] == ["gh", "secret", "set"]]


def test_sets_every_plugin_on_the_roster(market, gh):
    calls, _ = gh
    assert dispatch_secret.main([], market) == 0
    assert [c["args"][-1] for c in writes(calls)] == ["acme/widget", "acme/gadget"]


def test_named_plugins_only(market, gh):
    calls, _ = gh
    assert dispatch_secret.main(["gadget"], market) == 0
    assert [c["args"][-1] for c in writes(calls)] == ["acme/gadget"]


def test_the_token_is_trimmed_and_never_an_argument(market, gh):
    calls, _ = gh
    dispatch_secret.main([], market)
    assert all(TOKEN not in " ".join(c["args"]) for c in calls)
    assert {c["stdin"] for c in writes(calls)} == {TOKEN}


def test_the_probe_targets_the_marketplace(market, gh):
    calls, _ = gh
    dispatch_secret.main([], market)
    probe = next(c for c in calls if "dispatches" in " ".join(c["args"]))
    assert "repos/acme/market/dispatches" in probe["args"]
    assert probe["token"] == TOKEN


@pytest.mark.parametrize("failing", ["auth", "dispatch"])
def test_a_failed_check_writes_nothing(market, gh, failing):
    calls, state = gh
    state[failing] = False
    assert dispatch_secret.main([], market) == 1
    assert writes(calls) == []


def test_a_name_off_the_roster_is_noted_and_still_set(market, gh, capsys):
    calls, _ = gh
    assert dispatch_secret.main(["sprocket"], market) == 0
    assert "sprocket is not on" in capsys.readouterr().out
    assert [c["args"][-1] for c in writes(calls)] == ["acme/sprocket"]
