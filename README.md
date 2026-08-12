# shipyard

Shared build tooling for [chris-peterson's Claude Code plugins](https://github.com/chris-peterson/claude-marketplace).

Each plugin repo used to carry its own copy of the same build scripts —
`gen-plugin-json.py`, `gen-suite-json.py`, `changelog-prepend.py`, a docs
renderer. shipyard consolidates that logic so it lives here once, and the plugins
call it from CI.

## What it does

Each plugin's **source is the source of record** — `plugin.yml` for metadata and
presentation, and the skills/rules/hooks themselves for their own descriptions.
shipyard *projects* those into the generated, committed artifacts:

| Command | Projection |
|---|---|
| `shipyard gen-plugin-json` | `plugin.yml` → `.claude-plugin/plugin.json` |
| `shipyard gen-hooks-json` | `hooks/hooks.yml` → `hooks/hooks.json` |
| `shipyard gen-plugin-docs` | `plugin.yml` `suite:` → `docs/plugin-docs.json` |
| `shipyard gen-describe` | source (skills/rules/hooks) → `plugin.yml` `suite.describe` |
| `shipyard build-docs` | `skills/`,`rules/`,`guides/`,`templates/`,`SPEC.md`,`assets/` → `docs/` (+ plugin-docs.json, `docs/index.html` from `plugin.yml` `docs:`, and `docs/_home.md` from `suite:`) |
| `shipyard changelog` | release body → `CHANGELOG.md` (retitling a staged `## Unreleased` section in place) |
| `shipyard generate` | run every generator (write); `--dry-run` validates source + diffs pending output without writing (CI gate) |

Every command takes `--root <repo>` (default: the current directory), so
shipyard runs against a checked-out plugin, not itself.

Hooks are declared in `hooks/hooks.yml` — the source of record, a flat, commentable
list of `{event, matcher?, command, description}` — which shipyard projects into the
`hooks/hooks.json` Claude Code reads (same split as `plugin.yml` → `plugin.json`).
`gen-describe` reads the descriptions straight from `hooks.yml`, so no
`# DOCUMENTATION:` line in the hook scripts is needed.

## Aggregating a set of plugins

A marketplace or catalog site is the other kind of target. Its source of record is
a `plugins.yml` naming only what it owns — its identity, the roster, and the
roster's order — because everything shown *about* a plugin is already declared in
that plugin's `plugin.yml`:

```yaml
name: chris-peterson
description: Chris Peterson's Claude Code plugins
owner: chris-peterson
source: https://github.com/{owner}/{name}.git
artifacts: suite/artifacts.csv   # optional
plugins:
  - anchor
  - beacon
```

| Command | Projection |
|---|---|
| `shipyard roster` | `plugins.yml` → `name<TAB>url` pairs, resolvable with no plugin checkouts |
| `shipyard gen-marketplace-json` | `plugins.yml` + the plugins' `plugin.yml` → `.claude-plugin/marketplace.json` |
| `shipyard gen-plugins-js` | the plugins' `suite:` blocks → `docs/plugins.js` |
| `shipyard gen-deps-json` | the plugins' `suite.dependencies` → `docs/deps.json` |

`generate` dispatches on the manifest it finds at `--root`, so the same verb drives
both kinds: `plugin.yml` projects a plugin, `plugins.yml` projects an aggregator.
The plugins are read from sibling checkouts beside the aggregator — the layout the
aggregator's own sync step produces, which `roster` is what bootstraps.

## Using it from a plugin

A plugin's `.github/workflows/` are thin callers of shipyard's reusable
workflows, and its `scripts/shipyard` wrapper fetches the CLI — both pinned to
the `v1` tag. See a converted plugin (e.g.
[anchor](https://github.com/chris-peterson/anchor)) for the wrapper and the
workflow callers.

Only `docs/` is published, so art a page references from elsewhere in the repo
404s on the live site. `build-docs` copies the plugin's **resource paths** into
the published tree to close that (`assets/` unless the caller names others — see
the `resources` input on `actions/build-docs`), then fails the build on any local
reference the tree can't resolve. That last part is what makes the failure
visible: a missing image otherwise produces a green deploy and a blank page.

→ **[Docs](https://chris-peterson.github.io/shipyard)** — how it works, and a
before/after walk-through of converting a plugin.

Working on shipyard — repo layout, how to run the generators against a plugin
checkout, and the two contracts that reach outside this repo — is in
[AGENTS.md](./AGENTS.md), the same file the agents read.
actions/               composite actions plugins call via `uses:` in a step
.github/workflows/     reusable workflows plugins call via `uses:` in a job
