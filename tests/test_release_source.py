"""CHANGELOG.md as the release's source, and the bump level as its only input.

The release body used to be authored outside the repo at publish time, which made
it the source and left nothing constraining its shape: across the suite it took
at least three incompatible forms, and each one landed in a changelog permanently.
Reading the notes out of the file instead makes a mismatched or duplicated heading
unreachable rather than a shape the parser has to tolerate — shipyard writes the
only `## <version>` heading there is.

The refusals matter as much as the happy path. A release with nothing to say, or
one already published, cannot be undone once a tag names it.
"""
import pytest

from shipyard import changelog, version

TITLE = "# Changelog\n"


@pytest.fixture
def repo(tmp_path):
    def write(content):
        (tmp_path / "CHANGELOG.md").write_text(content)
        return tmp_path
    return write


# ---- the bump level --------------------------------------------------------

@pytest.mark.parametrize("current,level,expected", [
    ("1.2.3", "patch", "1.2.4"),
    ("1.2.3", "minor", "1.3.0"),
    ("1.2.3", "major", "2.0.0"),
    ("0.9.9", "minor", "0.10.0"),
])
def test_the_next_version_comes_from_the_current_one(current, level, expected):
    assert version.next_version(current, level) == expected


def test_a_minor_bump_zeroes_the_patch():
    assert version.next_version("2.4.7", "minor") == "2.5.0"


def test_an_unreadable_current_version_says_so():
    with pytest.raises(SystemExit, match="not a major.minor.patch version"):
        version.next_version("v1.2", "patch")


def test_an_unknown_level_names_the_ones_that_work():
    with pytest.raises(SystemExit, match="major, minor, patch"):
        version.next_version("1.2.3", "moderate")


# ---- shipyard's own version record ----------------------------------------

PYPROJECT = '''\
[project]
name = "shipyard"
# a comment the bump has no business touching
version = "1.0.0"
requires-python = ">=3.10"
'''


def test_the_bump_rewrites_one_line_and_leaves_the_file_alone(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)

    assert version.read_pyproject(tmp_path) == "1.0.0"
    version.write_pyproject("2.0.0", tmp_path)

    assert (tmp_path / "pyproject.toml").read_text() == \
        PYPROJECT.replace('version = "1.0.0"', 'version = "2.0.0"')


def test_a_pyproject_with_no_version_line_says_so(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "shipyard"\n')

    with pytest.raises(SystemExit, match="no `version"):
        version.read_pyproject(tmp_path)


def test_shipyards_own_version_is_readable():
    """The dogfood: the release reads this repo's version the same way a
    plugin's release reads plugin.yml's."""
    assert version.parse(version.read_pyproject("."))


# ---- reading the staged notes ---------------------------------------------

def test_the_staged_section_is_what_gets_released(repo):
    root = repo(TITLE + "\n## Unreleased\n\n- Added a thing\n\n## 1.1.0\n\n- Older\n")

    assert changelog.staged(root) == "- Added a thing"


def test_no_unreleased_section_is_a_failed_release(repo):
    root = repo(TITLE + "\n## 1.1.0\n\n- Older\n")

    with pytest.raises(SystemExit, match="no leading `## Unreleased` section"):
        changelog.staged(root)


def test_an_empty_unreleased_section_is_a_failed_release(repo):
    """Not a release with empty notes — a tag naming a version whose entry says
    nothing can't be fixed without moving it."""
    root = repo(TITLE + "\n## Unreleased\n\n## 1.1.0\n\n- Older\n")

    with pytest.raises(SystemExit, match="`## Unreleased` section is empty"):
        changelog.staged(root)


def test_a_missing_changelog_names_the_file(tmp_path):
    with pytest.raises(SystemExit, match="no CHANGELOG.md"):
        changelog.staged(tmp_path)


# ---- retitling in place ----------------------------------------------------

def test_retitle_renames_the_section_and_returns_its_body(repo):
    root = repo(TITLE + "\n## Unreleased\n\n- Added a thing\n\n## 1.1.0\n\n- Older\n")

    body = changelog.retitle("1.2.0", root)

    assert body == "- Added a thing"
    assert (root / "CHANGELOG.md").read_text() == \
        TITLE + "\n## 1.2.0\n\n- Added a thing\n\n## 1.1.0\n\n- Older\n"


def test_retitle_leaves_no_unreleased_heading_behind(repo):
    root = repo(TITLE + "\n## Unreleased\n\n- Added a thing\n")

    changelog.retitle("1.2.0", root)

    assert "Unreleased" not in (root / "CHANGELOG.md").read_text()


def test_releasing_a_version_already_in_the_file_is_refused(repo):
    root = repo(TITLE + "\n## Unreleased\n\n- Added a thing\n\n## 1.2.0\n\n- Older\n")

    with pytest.raises(SystemExit, match="already has a ## 1.2.0 section"):
        changelog.retitle("1.2.0", root)


# ---- reading a released section back out -----------------------------------

def test_the_published_body_is_the_committed_section(repo):
    """The property the whole inversion buys: one text, read twice."""
    root = repo(TITLE + "\n## Unreleased\n\n- Added a thing\n- And another\n")

    committed = changelog.retitle("1.2.0", root)

    assert changelog.section("1.2.0", root) == committed


def test_a_section_stops_at_the_next_version(repo):
    root = repo(TITLE + "\n## 1.2.0\n\n- Newer\n\n## 1.1.0\n\n- Older\n")

    assert changelog.section("1.2.0", root) == "- Newer"


def test_an_absent_section_says_so(repo):
    root = repo(TITLE + "\n## 1.1.0\n\n- Older\n")

    with pytest.raises(SystemExit, match="no ## 9.9.9 section"):
        changelog.section("9.9.9", root)
