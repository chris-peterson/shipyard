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
| `shipyard gen-suite-json` | `plugin.yml` `suite:` → `docs/suite.json` |
| `shipyard gen-describe` | source (skills/rules/hooks) → `plugin.yml` `suite.describe` |
| `shipyard build-docs` | `skills/`,`rules/`,`guides/`,`templates/`,`SPEC.md` → `docs/` (+ suite.json) |
| `shipyard changelog` | release body → `CHANGELOG.md` |
| `shipyard build` | run every generator |
| `shipyard check` | verify committed artifacts match source (CI gate) |

Every command takes `--root <plugin-repo>` (default: the current directory), so
shipyard runs against a checked-out plugin, not itself.

`gen-describe` requires each hook script to carry a `# DOCUMENTATION:` line below
its shebang — the one-line description shipyard derives its tooltip from. Missing
it is a hard error, not a fallback.

## Using it from a plugin

A plugin's `.github/workflows/` are thin callers of shipyard's reusable
workflows, and its `scripts/shipyard` wrapper fetches the CLI — both pinned to
the same ref: `@main` while shipyard is pre-1.0 (float to latest), moving to
semver tags once it reaches v1. See a converted plugin (e.g.
[anchor](https://github.com/chris-peterson/anchor)) for the wrapper and the
workflow callers.

→ **[Docs](https://chris-peterson.github.io/shipyard)** — how it works, and a
before/after walk-through of converting a plugin.

## Layout

```
src/shipyard/          the CLI + generators
.github/workflows/     reusable workflows plugins call via `uses:`
```
