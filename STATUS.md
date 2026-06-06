# shipyard — Spec Status

Spec: [SPEC.md](SPEC.md)

| ID | Requirement | Status |
|----|-------------|--------|
| CLI-01 | `shipyard init` scaffolds canonical source files and directory structure | Unmet |
| CLI-02 | `shipyard build` regenerates all per-target outputs in place | Unmet |
| CLI-03 | `shipyard check` verifies outputs match sources, exits non-zero on drift | Unmet |
| CLI-04 | `shipyard preview <target>` installs locally under the named target | Unmet |
| CLI-05 | `shipyard migrate` produces canonical sources from an existing Claude-format plugin | Unmet |
| CLI-06 | `shipyard build-docs` expands template variables and target-variant blocks | Unmet |
| SCH-01 | `plugin.yaml` captures plugin identity and target list | Unmet |
| SCH-02 | `hooks.yaml` describes hooks in a neutral vocabulary with per-target mappings | Unmet |
| SCH-03 | Skills, agents, MCP config are canonical sources shared across targets unchanged | Unmet |
| BLD-01 | Build produces Claude manifest at `.claude-plugin/plugin.json` | Unmet |
| BLD-02 | Build produces Copilot manifest at `.github/plugin/plugin.json` | Unmet |
| BLD-03 | Build produces Claude hook config at `hooks/claude.json` | Unmet |
| BLD-04 | Build produces Copilot hook config at `hooks/copilot.json` | Unmet |
| BLD-05 | Generated files are identifiable as generated and reference their source | Unmet |
| MKT-01 | `shipyard build --marketplace` produces Copilot registry at `.github/plugin/marketplace.json` | Unmet |
| MKT-02 | Copilot marketplace projection adapts field structure and source references | Unmet |
| DOC-01 | Preprocessor supports standard template variable vocabulary | Unmet |
| DOC-02 | Target-variant content blocks render as inline tab controls | Unmet |
| DOC-03 | Tab component syncs selection across groups, persists it, honors URL param | Unmet |
| DOC-04 | Default target selection is Claude | Unmet |
| DOC-05 | `build-docs` generates a requirements page from a sextant project's `SPEC.md` | Unmet |
| DOC-06 | With a `STATUS.md`, page shows only met reqs (suppress unmet/FUT); else all | Unmet |
| DOC-07 | Generated page shows requirement text only, not maintainer-facing status | Unmet |
| DOC-08 | Generated requirements page is de-emphasized low in the sidebar/TOC | Unmet |
| VAL-01 | `shipyard check` validates build and doc outputs in one invocation | Unmet |
| VAL-02 | `shipyard check` identifies affected outputs and exits non-zero on drift | Unmet |
| SHP-01 | `init` scaffolds single-file CLI at `scripts/<name>` + one-line slash shim | Unmet |
| SHP-02 | Scaffolded CLI resolves plugin root from env or its own file location | Unmet |
| SHP-03 | `--help`/`-h`/`help` → stdout exit 0; no-args/unknown → stderr exit non-zero | Unmet |
| SHP-04 | `init` scaffolds a wrapper skill as the CLI's conversational entry point (corollary to `--help`) | Unmet |
| SHP-05 | CLI failures write actionable stderr message and exit non-zero, no fallback | Unmet |
| OUT-01 | CLI resolves color by precedence: `--color` flag, env, then TTY | Unmet |
| OUT-02 | Live/interactive views require a TTY; one-shot command stays scriptable | Unmet |
| FRS-01 | `init` scaffolds SessionStart hook flagging wrapper-vs-plugin.json version drift | Unmet |
| FRS-02 | `init` scaffolds PATH installer as on-PATH wrapper, not a shell alias | Unmet |
| CMP-01 | Scaffolded CLI embeds completion as a constant, installs via `completions` | Unmet |
| CMP-02 | `install-cli` installs completion via a shared helper in the same command | Unmet |
| CMP-03 | `init` scaffolds PostToolUse hook reminding to reconcile completion on CLI edit | Unmet |
| VER-01 | CLI version flag reads from `plugin.json` at runtime, no version constant | Unmet |
| VER-02 | `plugin.json` version is the single source of truth for the plugin version | Unmet |
| VER-03 | `init` freezes any required auxiliary manifest's version at a private stub | Unmet |
| VER-04 | `shipyard check` flags auxiliary manifest version diverging from `plugin.json` | Unmet |
| STA-01 | Scaffolded CLI stores state outside the plugin install directory | Unmet |
| STA-02 | CLI derives state dir from plugin root, not from `CLAUDE_PLUGIN_DATA` alone | Unmet |
| DST-01 | `init` scaffolds `CHANGELOG.md` and a README "Updating" section | Unmet |
| PUB-01 | Plugin installable via direct `git clone` and via a marketplace, same sources | Unmet |
| PUB-02 | Same plugin source registrable in multiple marketplaces, optionally rebranded | Unmet |
| PUB-03 | Marketplace projection preserves each entry's advertised name and source | Unmet |
| AMB-01 | `init` scaffolds SessionStart hook emitting the plugin's `rules/*.md` | Unmet |
| AMB-02 | Between-invocation invariants are ambient rules; procedure stays in skills | Unmet |
