import pytest

from shipyard import changelog

TITLE = "# Changelog\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A plugin root whose CHANGELOG.md the test seeds, released as 1.2.0 by
    default. Returns a helper that writes the file, runs the command, and hands
    back the result."""
    def release(content, *, version="1.2.0", body="- Added a thing"):
        (tmp_path / "CHANGELOG.md").write_text(content)
        monkeypatch.setenv("VERSION", version)
        monkeypatch.setenv("BODY", body)
        changelog.run(tmp_path)
        return (tmp_path / "CHANGELOG.md").read_text()
    return release


def test_prepends_when_there_is_no_staged_section(repo):
    out = repo(TITLE + "\n## 1.1.0\n\n- An older thing\n")
    assert out == TITLE + "\n## 1.2.0\n\n- Added a thing\n\n## 1.1.0\n\n- An older thing\n"


def test_staged_section_is_retitled_not_duplicated(repo):
    out = repo(TITLE + "\n## Unreleased\n\n- Added a thing\n\n## 1.1.0\n\n- An older thing\n")
    assert "Unreleased" not in out
    assert out.count("## 1.2.0") == 1
    assert out == TITLE + "\n## 1.2.0\n\n- Added a thing\n\n## 1.1.0\n\n- An older thing\n"


def test_divergent_release_body_wins_and_is_reported(repo, capsys):
    out = repo(TITLE + "\n## Unreleased\n\n- Staged wording\n", body="- Published wording")
    assert "Unreleased" not in out
    assert "- Staged wording" not in out
    assert out == TITLE + "\n## 1.2.0\n\n- Published wording\n"
    assert "- Staged wording" in capsys.readouterr().err


def test_empty_release_body_keeps_the_staged_notes(repo):
    out = repo(TITLE + "\n## Unreleased\n\n- Staged wording\n", body="")
    assert out == TITLE + "\n## 1.2.0\n\n- Staged wording\n"


def test_bracketed_and_cased_unreleased_headings_are_recognized(repo):
    out = repo(TITLE + "\n## [UNRELEASED]\n\n- Added a thing\n")
    assert out == TITLE + "\n## 1.2.0\n\n- Added a thing\n"


def test_unreleased_below_a_released_section_is_left_alone(repo):
    """Only a *leading* Unreleased section is the staging area; one buried below
    a released section is somebody's history, not this release's notes."""
    seeded = TITLE + "\n## 1.1.0\n\n- An older thing\n\n## Unreleased\n\n- Ancient\n"
    out = repo(seeded)
    assert out == TITLE + "\n## 1.2.0\n\n- Added a thing\n" + seeded[len(TITLE):].rstrip("\n") + "\n"


def test_republishing_the_same_version_changes_nothing(repo):
    seeded = TITLE + "\n## 1.2.0\n\n- Added a thing\n"
    assert repo(seeded) == seeded


def test_republish_guard_wins_over_a_staged_section(repo):
    seeded = TITLE + "\n## Unreleased\n\n- Staged wording\n\n## 1.2.0\n\n- Added a thing\n"
    assert repo(seeded) == seeded


def test_missing_title_is_an_error(repo):
    with pytest.raises(SystemExit):
        repo("No heading here\n")
