# Cutting a release

Releasing is one `workflow_dispatch` whose only input is the bump level. CI derives the version, retitles the notes, commits, tags that commit, and publishes. See [the release flow](how-it-works.md#the-release-flow) for the sequence.

This page is the contract for whoever drives it, because it is rarely the same *whoever* twice: a maintainer from the terminal one week, an agent from a different harness the next. Anything a harness would otherwise have to remember on its own lives here.

## Writing the notes is the release

Releasing is one sitting, and it starts before the dispatch:

```bash
git log <last-tag>..main --no-merges
```

Read what landed, write it up under `## Unreleased` in `CHANGELOG.md`, commit that, then dispatch with the bump the notes imply. **The bump follows from the notes, not the other way around** — you can't know whether a release is major, minor, or patch until you've read what's in it, and that is the same reading that produces the notes. One judgment, so it happens at one time.

```markdown
# Changelog

## Unreleased

### Added
- The thing, described by what it does for someone using this

### Fixed
- The bug, described by what stopped happening

## 1.1.0
- …
```

Writing them together is also what lets them be *shaped*. A release read whole can be grouped, and can carry a migration section; notes accrued one commit at a time arrive in commit order, and nobody goes back to reorganize them.

**No section, no release.** A missing or empty `## Unreleased` fails the run. A tag naming a version whose changelog entry says nothing cannot be fixed afterwards without moving the tag.

## Driving it

1. `git log <last-tag>..main` — read what landed.
2. Write the `## Unreleased` section. Commit and push it.
3. Dispatch the release workflow, choosing `major`, `minor`, or `patch`.
4. Nothing else. Don't bump the version, don't retitle the section, don't create the tag or the release.

Step 2 being its own commit is what gets the notes reviewed: a diff you look at before releasing, rather than prose composed in a dispatch form and seen by nobody.

## What the workflow owns

Doing any of these by hand lands a second, conflicting commit — or a tag that disagrees with what is in it:

- **The version.** Derived by bumping what `plugin.yml` already records.
- **The `## <version>` heading.** `shipyard release` retitles your section in place. Nothing else writes a heading, which is why a duplicated one is impossible rather than something the parser tolerates.
- **The generated artifacts**, resynced as a backstop. The projection job already committed them when the source changed, so a release ordinarily finds nothing to resync.
- **The commit, then the tag on it,** in that order — so the artifacts at the tag report the version the tag names.
- **The GitHub Release**, published with the changelog section as its body.
- **The marketplace rebuild.**

## Notes written earlier

Nothing stops a change from adding to `## Unreleased` when it lands, and nothing checks that it did — the section only has to exist and say something at release time. Worth doing for a change whose *why* would be hard to reconstruct later, or where whoever releases won't be whoever wrote it. The default is release time, because that is when the whole shape is visible and when the bump has to be decided anyway.
