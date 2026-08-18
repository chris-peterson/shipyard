# Cutting a release

Publishing a GitHub Release on a plugin is the whole trigger — the tag carries the version, the release body carries the notes, and shipyard's reusable workflow does everything downstream. See [the release flow](how-it-works.md#the-release-flow) for the sequence.

This page is the contract for whoever drives that, because it is rarely the same *whoever* twice: a maintainer from the terminal one week, an agent from a different harness the next. Anything a harness would otherwise have to remember on its own lives here.

## What the workflow owns

Publishing the release hands these to CI. Doing any of them by hand lands a second, conflicting commit:

- **The version.** It comes from the tag (`v1.2.0` → `1.2.0`). CI writes it into `plugin.yml` and regenerates `.claude-plugin/plugin.json` — don't bump `plugin.yml` yourself.
- **The generated artifacts.** `plugin.json`, `hooks.json`, `suite.describe`, and `docs/` are resynced from source at release — a backstop, not the writer. The projection job already committed them when the source changed, so a release ordinarily finds nothing to resync.
- **`CHANGELOG.md`.** The release body is written into a `## <VERSION>` section. Don't hand-write that section — see below for where notes *do* get written by hand.
- **The commit on `main`** and the marketplace rebuild.

## Staging notes under `## Unreleased`

Notes are best written while the change is fresh, which is during the sprint, not at the moment someone cuts a release. So keep a leading `## Unreleased` section in `CHANGELOG.md` and write into it as work lands:

```markdown
# Changelog

## Unreleased

- Reconcile a staged `## Unreleased` section instead of prepending beside it

## 1.1.0

- …
```

At release, **the release body should be that section's content.** `shipyard changelog` then *retitles* the staged section to `## <VERSION>` in place rather than adding a second copy above it — which is what used to leave the same notes in the file twice, with a stale `## Unreleased` heading below them.

Two ways it can go otherwise, both reported on stderr in the job log:

| Situation | What lands |
|---|---|
| Release body differs from the staged notes | The release body wins — it's what was published and what readers saw. The staged text is echoed to the log. |
| Release body is empty | The staged notes are kept as the section. |

Re-publishing the same release is a no-op: an existing `## <VERSION>` section leaves the file untouched.

## Checklist for the harness driving it

1. Read the leading `## Unreleased` section of `CHANGELOG.md`; it is the draft of the release notes.
2. Choose the semver bump from what's in it, and tag `v<major>.<minor>.<patch>`.
3. Publish the release with that section's content as the body — don't recompose the notes from the commit log, or the two will disagree and the staged wording is discarded.
4. Leave `plugin.yml`, `CHANGELOG.md`, and the generated artifacts alone. CI commits them.
5. After CI pushes, the next contributor opens a fresh `## Unreleased` section when they have something to note.
