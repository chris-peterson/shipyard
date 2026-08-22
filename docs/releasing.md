# Cutting a release

Two commands in the checkout you already have open.

```bash
shipyard release      # drafts this release's notes into CHANGELOG.md, then stops
# …rewrite the drafted lines into notes…
shipyard release      # previews, asks once, then commits, tags, pushes, publishes
```

Which half runs is decided by `CHANGELOG.md`, not by a flag. An empty or absent `## Unreleased` means the notes don't exist yet, so it drafts them and stops. A section with notes in it means the release is ready, so it ships. Re-running is how you get from one to the other, and re-running after a failure picks up wherever the file now is.

There is no workflow to dispatch, no bump level to choose in a form, and nothing to look up before you start.

## The first half: what landed, drafted

`shipyard release` reads the commits since the last `vX.Y.Z` tag and writes them into `CHANGELOG.md` under `## Unreleased`, with the sections to sort them into:

```markdown
## Unreleased

<!-- shipyard drafted this from the 3 commits since v1.2.0.
     Move each line below into the section that applies and rewrite it for
     someone *using* this, then delete this comment and the Unsorted
     heading. -->

### Added

### Changed

### Fixed

### Unsorted

- Let a plugin declare its own pre-render step (40bd2be)
- Stop dropping the last documented flag (456cdb6)
- Teach the parser about command groups (63fd8a5)
```

That's a worksheet, not notes. A commit subject is written for someone reading this repo's history; a changelog line is written for someone *using* it, and no mechanical rewrite of the first produces the second. What the draft removes is the blank page and the file mechanics, which is where the cost actually was.

Sorting it is the release's one piece of real work, and it's the same reading that picks the version — so both happen here, once. The notes stay uncommitted while you write them; the release commit picks them up.

**A worksheet cannot be published.** Releasing with the comment or the `### Unsorted` heading still in place is refused by name. A half-sorted section is never re-drafted over either — `--draft` is how you ask for a fresh worksheet, and it says so.

## The second half: preview, then one confirmation

Run it again and everything you'd otherwise learn from a finished CI run prints first:

```text
  1.2.0 → 1.3.0   (minor, from `### Added`)
  recorded in plugin.yml, projected into .claude-plugin/plugin.json

release body ──────────────────────────────────────────────────────
### Added

- **Command groups in the generated reference.** A CLI's page can now be
  organised into sections instead of one flat alphabetical list.

### Fixed

- The last flag a command documents is no longer dropped from its manifest.
───────────────────────────────────────────────────────────────────

  commit   Release v1.3.0
  tag      v1.3.0  (on that commit)
  push     main and v1.3.0 together, atomically
  publish  v1.3.0, with the body above

release this as minor? [y/N/major/minor/patch]
```

**The level comes from the headings you wrote**, not from a dropdown:

| The notes' headings | Level |
| --- | --- |
| `### Removed`, `### Breaking` | major |
| `### Added`, `### Deprecated` | minor |
| anything else, or no headings | patch |

Empty headings left over from the worksheet don't count, so a skeleton doesn't make every release a minor one.

A heading names the *kind* of change, not whose contract it broke, so the inference errs in both directions and the preview is where you catch it:

- **Under.** A breaking change filed under `### Changed` reads as a patch. Nothing in the prose distinguishes it from a rewording.
- **Over.** A `### Removed` entry for something no consumer could reach — shipyard's own CI, an internal helper — reads as major.

That's why the level and the heading that decided it print above the prompt, and why the prompt takes a level as an answer. The mapping leans toward over-bumping because the two mistakes don't cost the same: an over-bump spends a version number, an under-bump ships a break to someone pinning a range.

Answering with a level re-runs rather than shipping, so the plan you approve is always the plan you were shown. `--bump major` does the same thing in one step.

Answering anything but `y` writes nothing.

## What it does once you say yes

In this order, because the order is what makes the release, the tag, and the compare link agree:

1. Retitles your `## Unreleased` to `## 1.3.0`.
2. Bumps `plugin.yml` and projects `.claude-plugin/plugin.json` from it.
3. Commits all three as `Release v1.3.0` — so the notes and the version are one commit, and `v1.2.0...v1.3.0` contains the changelog.
4. Tags `v1.3.0` on that commit.
5. Pushes the branch and the tag in **one** transaction (`--atomic`), so there is no window where the tag exists and the commit it names doesn't.
6. Publishes the release with the committed section as its body, byte for byte.

The three things that used to disagree now can't: the body *is* the section, the tag names a commit that already carries `## 1.3.0` and the bumped `plugin.json`, and the compare link contains all of it.

## What stops a release before anything is written

Every one of these used to be a red CI run you had to open and read. They all run in the checkout, before the first write.

| Refusal | Why it matters |
| --- | --- |
| Not on `main`, or behind the remote | the tag would name something other than the branch head |
| Uncommitted changes outside `CHANGELOG.md` | a release commits the notes and the bump, nothing else |
| Unpushed commits on `main` | they haven't been through the projection job yet |
| No `CHANGELOG.md`, or an empty `## Unreleased` | a tag naming a version whose entry says nothing can't be fixed without moving the tag |
| `## Unreleased` still the worksheet | a worksheet published as notes is permanent |
| `plugin.json` or `hooks.json` doesn't match its source | a commit the projection job still owes this branch, which a release would land *after* the tag |
| `vX.Y.Z` already exists | releasing a version twice |
| `gh` not authenticated | the publish would fail after the tag was already pushed |

## A release never builds what it releases

The projections a release checks are the ones that read YAML and write JSON — `plugin.json` and `hooks.json`. The CLI manifest is deliberately not among them, because verifying it means running your CLI, and running your CLI means building it first.

That exclusion is the point. The step this replaced ran the full `generate` inside the release job, on a checkout with nothing built ahead of it. For a plugin whose committed entry point imports its dependencies at runtime, the CLI exited non-zero there and the release died *before* committing the version bump — leaving the repo mid-release, and needing a change to the plugin's own `cli: invoke:` to work around a step that had no business running there at all.

So a release now reads only what it can read with pyyaml. If a projection needing your toolchain has drifted, that's the projection job's commit to make, and it makes it in your own build. Nothing about cutting a release depends on your build working.

## What CI still does

One thing, because it's the one thing that needs a repo secret: the marketplace rebuild. A plugin's whole `release.yml` becomes

```yaml
on:
  release:
    types: [published]

jobs:
  notify:
    uses: chris-peterson/shipyard/.github/workflows/notify-marketplace.yml@v2
    secrets: inherit
```

`MARKETPLACE_DISPATCH_TOKEN` can dispatch across repositories where the default `GITHUB_TOKEN` can't, and a secret only exists inside Actions. Because the release is published with your own credentials rather than Actions' token, the `release: published` event carries through and starts this run.

## Releasing shipyard itself

The same command, from a shipyard checkout. `pyproject.toml` carries the version in place of `plugin.yml`, and one extra step runs: the `vX` alias tag moves onto the new release, since consumers pin `uses: …@v2` and that has to keep resolving to the newest release on the line. A `vX` **branch** existing at the same time is refused up front — which one a consumer's `@v2` resolves to isn't something to leave to chance.
