# Cutting a release

Releasing is one `workflow_dispatch` whose only input is the bump level. CI derives the version, retitles the notes you already wrote, commits, tags that commit, and publishes. See [the release flow](how-it-works.md#the-release-flow) for the sequence.

This page is the contract for whoever drives it, because it is rarely the same *whoever* twice: a maintainer from the terminal one week, an agent from a different harness the next. Anything a harness would otherwise have to remember on its own lives here.

## Notes are written as work lands, not at release time

`CHANGELOG.md` is the source. Keep a leading `## Unreleased` section and write into it in the same change request as the work it describes:

```markdown
# Changelog

## Unreleased

- Reconcile a staged `## Unreleased` section instead of prepending beside it

## 1.1.0

- …
```

Two things follow. The notes get **reviewed**, in the diff next to the code they describe, instead of being composed from memory by whoever happens to cut the release. And the release body becomes a projection of this file rather than its source, so the two cannot disagree.

**No section, no release.** A missing or empty `## Unreleased` fails the run. That is deliberate: a tag naming a version whose changelog entry says nothing cannot be fixed afterwards without moving the tag.

## Driving it

1. Check that `## Unreleased` says what you want the release to say. That text *is* the release body.
2. Run the repo's release workflow, choosing `major`, `minor`, or `patch`.
3. Nothing else. Don't bump the version, don't retitle the section, don't create the tag or the release.

The bump level rather than a literal version removes the class of typo where the tag and the version disagree, and it is the input you can supply without looking anything up.

## What the workflow owns

Doing any of these by hand lands a second, conflicting commit — or a tag that disagrees with what is in it:

- **The version.** Derived by bumping what `plugin.yml` already says.
- **The `## <version>` heading.** `shipyard release` retitles your staged section in place. Nothing else writes a heading, which is why a duplicated one is now impossible rather than something the parser tolerates.
- **The generated artifacts**, resynced as a backstop. The projection job already committed them when the source changed, so a release ordinarily finds nothing to resync.
- **The commit, then the tag on it,** in that order. The tag names a commit that already carries its own version — so `plugin.json` at the tag reports the version the tag names.
- **The GitHub Release**, published with the changelog section as its body.
- **The marketplace rebuild.**

## After it runs

Open a fresh `## Unreleased` section when you next have something to note. Don't leave an empty one behind: an empty section and a missing one both fail the next release, and the empty one reads like it was meant to be filled.
