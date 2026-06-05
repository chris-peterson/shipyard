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
| VAL-01 | `shipyard check` validates build and doc outputs in one invocation | Unmet |
| VAL-02 | `shipyard check` identifies affected outputs and exits non-zero on drift | Unmet |
