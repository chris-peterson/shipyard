# Changelog

What changed for a repo that calls shipyard's workflows and actions. Written as
work lands, under `## Unreleased`; the release retitles that section and
publishes it as the release body, so this file and the release say one thing.

shipyard is pinned by ref, so a version here is a tag you can point `uses:` at.
`vX.Y.Z` is immutable; `vX` moves to the newest release on its line. Two majors
are live while the projection shape is piloted: `v1` is the workflow-only shape,
`v2` is everything below.

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
