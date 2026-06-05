# shipyard

A build tool for multi-target AI assistant plugins.

Write your plugin once — skills, agents, MCP config — and `shipyard` generates
the runtime-specific manifests and hook configs so the same plugin works on
Claude Code and GitHub Copilot CLI without hand-maintaining parallel files.

→ [Docs](https://chris-peterson.github.io/shipyard) *(coming soon)*

## How it works

Each plugin repo has a single canonical source: a `plugin.yaml` describing
metadata and targets, a `hooks.yaml` describing hook behaviors in a neutral
vocabulary, plus your skills and agents (which are identical across runtimes).

`shipyard build` reads those sources and writes the per-target artifacts in
place. Generated files are committed alongside their sources so diffs are
visible in PRs. `shipyard check` keeps them honest in CI.

## Commands

| Command | What it does |
|---|---|
| `shipyard init` | Scaffold a new plugin repo |
| `shipyard build` | Regenerate all per-target manifests and hook configs |
| `shipyard check` | Validate generated files match their sources (CI gate) |
| `shipyard preview <target>` | Install locally for smoke testing |
| `shipyard migrate` | Import an existing Claude-only plugin |
| `shipyard build-docs` | Preprocess docs for target-aware rendering |

## Install

*(coming soon — will be published to npm)*

## Repository layout

```
src/        source code
test/       tests
docs/       documentation site source
```

## Development

```bash
just build   # compile
just test    # run tests
just check   # validate generated fixtures
```

## Contributing

Open an issue or PR. See [SPEC.md](SPEC.md) for the feature spec and
[STATUS.md](STATUS.md) for current coverage.
