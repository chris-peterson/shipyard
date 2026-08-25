# Changelog

What changed for a repo that calls shipyard's workflows and actions. Written
under `## Unreleased` when cutting a release; the release retitles that section
and publishes it as the release body, so this file and the release say one thing.
See [Cutting a release](https://chris-peterson.github.io/shipyard/#/releasing).

shipyard is pinned by ref, so a version here is a tag you can point `uses:` at.
`vX.Y.Z` is immutable; `vX` moves to the newest release on its line. Two majors
are live while the projection shape is piloted: `v1` is the workflow-only shape,
`v2` is everything below.

## 2.3.1

### Fixed

- **`shipyard release --root <elsewhere>` publishes to the repo it was pointed
  at.** `gh` reads which repo it acts on from its working directory, and only
  that call was untargeted, so a release cut from outside the target checkout
  bumped, tagged, moved the alias, and pushed the right repo, then published the
  notes as a release on whichever repo the shell was sitting in.

## 2.3.0

### Added

- **A plugin can declare who it reaches.** A `relevance:` block under
  `marketplace:` in `plugin.yml` projects into the plugin's marketplace entry,
  where Claude Code reads it to suggest the plugin to sessions whose working
  directory, commands, hostnames, files read, or package-manifest dependencies
  match. Nothing surfaces until an administrator allowlists the marketplace in
  `pluginSuggestionMarketplaces`.
- **A plugin can declare the plugins it needs.** A top-level `dependencies:`
  list projects into `.claude-plugin/plugin.json`, so installing the plugin
  installs them too. Entries are a plugin name, or a mapping with `name` and an
  optional npm `version` range and `marketplace`. This is a different field from
  `suite.dependencies`, which draws the doc site's soft-edge graph and installs
  nothing.
- **A marketplace can allow its plugins to depend across marketplaces.**
  `allowCrossMarketplaceDependenciesOn:` in `plugins.yml` publishes into
  `marketplace.json`, and `gen-marketplace-json` checks each plugin's
  cross-marketplace dependency against it — so one that would fail at install
  fails at projection instead.
- **Both blocks are validated where Claude Code stays silent.** A misspelled
  signal name, an unknown key under `relevance`, a repeated pattern, a `version`
  that isn't a semver range, a misspelled key on a dependency object, and a
  self- or duplicate dependency are all errors. Claude Code loads past every one
  of them and reports none, so the plugin quietly does less than its owner
  wrote. [Suggestions and dependencies](https://chris-peterson.github.io/shipyard/#/suggestions-and-dependencies)
  has the split against `claude plugin validate --strict`.

### Fixed

- **`shipyard release` names the flag, not a heading, when `--bump` set the
  level.** The preview line read ``(major, from `### --bump`)``, which reads as a
  heading in the notes that decided it.

### Known gaps

- **A `version` constraint doesn't resolve yet.** Claude Code matches ranges
  against `{plugin-name}--v{version}` tags; `shipyard release` writes
  `v{version}`. Declare dependencies without a `version` until the release flow
  writes the prefixed tag.

## 2.2.0

### Added

- **`shipyard release` cuts a release from your own checkout**, in two runs of
  one command. The first reads the commits since the last `vX.Y.Z` tag and
  drafts them into `CHANGELOG.md` under `## Unreleased`, with the sections to
  sort them into; you rewrite those lines into notes; the second prints the
  version, the exact body it will publish, and the refs it will write, asks
  once, then commits the notes and the bump as one commit, tags it, pushes both
  atomically, and publishes. Which half runs is decided by the file rather than
  a flag, so re-running is how you advance and how you resume after a failure.
- **The bump level is read back from the notes**, not chosen in a form. A
  `### Removed` or `### Breaking` heading with content under it means major,
  `### Added` or `### Deprecated` means minor, anything else patch; empty
  headings left by the draft don't count. The level and the heading that decided
  it print above the confirmation, which takes `major`, `minor`, or `patch` as
  an answer, and `--bump` overrides outright.
- **Every refusal now happens before the first write**, in the checkout: a
  worksheet still unsorted, an empty `## Unreleased`, a version already tagged,
  a `plugin.json` that disagrees with `plugin.yml`, unpushed commits, a dirty
  tree outside the changelog, a `vX` alias that is also a branch, `gh` not
  authenticated. Each of these was a red run to open and read, and the alias
  check in particular used to fire *after* the bump commit already existed.
- **A release no longer runs the plugin's own build.** It checks the projections
  it can check with pyyaml alone — `plugin.json` and `hooks.json` — and refuses
  when one disagrees with its source, because that is the projection job's commit
  to make. The CLI manifest is excluded by design: verifying it means running the
  plugin's CLI. The step this replaces ran the full `generate` inside the release
  job on a checkout with nothing built ahead of it, so a plugin whose committed
  entry point imports its dependencies at runtime saw the CLI exit non-zero and
  the release die before it committed the version bump — a failure that had to be
  worked around in the plugin's own `cli: invoke:`.
- **`notify-marketplace.yml`** is the reusable workflow a converted plugin calls
  on `release: published`, holding the one part of a release that needs a repo
  secret. A plugin's whole release.yml becomes four lines.

### Changed

- **The release commit carries the notes, the version, and the projected
  `plugin.json` together**, so the compare link between two tags contains the
  changelog entry for the newer one. The branch and its tag are pushed in one
  atomic transaction, so no window exists in which the tag names a commit that
  is not there yet.
- **`stage-release` is the new name of the pure step** the dispatched
  `release.yml` calls (it was `release`, which is now the local driver). Callers
  of `release.yml` are unaffected — the workflow pins the shipyard line it
  belongs to, so the rename travels with it.

### Removed

- **`cut-release.yml`.** shipyard releases itself with `shipyard release`, the
  same command it gives a plugin, including the `vX` alias move its own
  consumers pin. `release.yml` stays for plugins that have not converted.

## 2.1.0

### Added

- **`docs: pre_render:`** declares command(s) a plugin runs itself, from its
  root, before `build-docs` renders or link-checks anything — for pages
  shipyard has no renderer for (a CLI-specific gallery, a domain table built
  from a plugin's own source). Without it, a plugin publishing such a page had
  to get its own CI job's step order right independently at every call site
  that reaches `build-docs` (`build-docs` itself, and `generate`, which runs it
  internally) — and ClaudeWatch's conversion shipped that wrong in three of
  four places before the gap was worth closing here instead of in every
  consumer.
- **`cli:` gains `lede`, `groups`, `examples`, and `notes`** — a CLI's
  generated reference page can be organized into sections with a lede,
  worked examples, and per-command prose, instead of the flat alphabetical
  list `--help` alone produces. Declared in `plugin.yml` beside `invoke`,
  `engine`, and `manifest`; declaring nothing keeps today's flat page. The
  generator refuses any disagreement with what the CLI actually documents —
  a group naming a command the help doesn't have, or a documented command in
  no group, fails the run rather than shipping a page silently missing it.
  The committed manifest stays pure grammar (the declared organization is
  merged in only when `build-docs` renders the page), so a diff to it is
  still always a change to the CLI's contract, and every manifest written
  before these fields stays valid under the unchanged `v1` schema.

## 2.0.0

### Changed

- **Every generated artifact is written by CI.** `actions/project` runs the
  projectors on each push and commits the result to the branch, so a committed
  artifact matches its source at all times instead of only after a release, and
  the diff a reviewer approves is the change that lands. `hooks.json` had no CI
  writer at all before this, so a merged `hooks.yml` edit shipped a mismatched
  `hooks.json` to every install.
- **Resource paths are declared in `plugin.yml`, not passed in.** Name them under
  `docs: resources:`. The `resources` input is gone from `actions/build-docs`,
  `actions/project`, and `deploy-docs.yml`. Every projector input now comes from
  the checkout, which is what lets a local run reproduce CI's exactly.
- **`generate` writes and only writes.** `--dry-run`, every generator's
  `preview()`, and the `preview.yml` workflow are gone. The branch carries the
  real projection, so the diff is the preview.
- **`gen-cli-manifest` has no `--check` gate**, and `preview.yml`'s `cli-build`
  input went with it. The grammar reaches the diff by being pushed there.

### Added

- **`gen-cli-manifest`** records a CLI's documented grammar as a committed
  manifest, and `build-docs` renders it as a command reference page. Declare the
  CLI in `plugin.yml`'s `cli:` block.
- **A local read of the projection.** `uvx --from
  'git+https://github.com/chris-peterson/shipyard@v2' shipyard generate` runs the
  same CLI the action runs, with no checkout and no install — for seeing why a
  projection job went red. It reads; CI stays the only writer.

### Fixed

- **`deploy-docs.yml` and `release.yml` pinned the wrong line.** Each names
  shipyard itself, and both said `v1`. With two majors live, a caller at `@v2`
  would have built its docs with v1's renderer and run v1's generators over its
  sources during a release.
- **Malformed source failed as a traceback.** A `hooks.yml` written as a bare
  list died with `AttributeError: 'list' object has no attribute 'get'`. The file
  and the shape it needed are now named.
- **`gen-describe` filed `describe:` under the wrong key.** The block was
  appended at end-of-file, so a `plugin.yml` with anything after `suite:` got it
  nested under that key instead — valid YAML with `suite.describe` absent, and
  the projections reading it silently empty. A `suite:` written inline
  (`{sessions: []}`) produced a file that no longer parsed at all.

### Migrating from `v1`

A repo on `@v1` keeps working; nothing here reaches it. To move:

1. Replace the `preview.yml` caller with a projection job: grant it
   `contents: write`, check out `${{ github.head_ref }}`, run your own build,
   then `chris-peterson/shipyard/actions/project@v2`.
2. Move any `resources:` input into `plugin.yml`'s `docs: resources:`.
3. Delete `scripts/shipyard` and any `just` target or pre-commit hook that ran it.
4. Git-ignore rendered `docs/`, so the projection doesn't commit it.
5. Repin the remaining callers at `@v2`.
