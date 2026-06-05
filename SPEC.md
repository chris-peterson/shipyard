# shipyard — Specification

A CLI tool that reads a neutral `plugin.yaml` canonical source and generates
target-specific manifests and hook configs in place, so a single plugin repo
can be consumed by Claude Code and GitHub Copilot CLI without maintaining
parallel hand-authored files.

Requirements use [EARS syntax](https://alistairmavin.com/ears) — each is one of:
Ubiquitous (`The <system> shall …`), State-Driven (`While …`), Event-Driven
(`When …`), Optional (`Where …`), or Unwanted Behaviour (`If … then …`).

## Concepts

- **plugin** — a set of skills, agents, MCP configs, and hook configs distributed as a unit from a git repo
- **target** — a runtime consumer (Claude Code, GitHub Copilot CLI) with its own manifest format and hook event vocabulary
- **canonical source** — files authored by hand and never overwritten by shipyard (`plugin.yaml`, `hooks.yaml`, skills, agents, `.mcp.json`)
- **generated file** — a file produced by `shipyard build` from canonical sources; committed to git but not hand-edited
- **manifest** — a target-specific JSON descriptor read by the plugin runtime (e.g., `.claude-plugin/plugin.json`, `.github/plugin/plugin.json`)
- **hook** — a shell command wired to a target runtime event (e.g., `SessionStart`)
- **projection** — the transformation from canonical source to a specific target's output format
- **marketplace** — a registry that lists plugins available for install

## Feature groups

The requirements below are organized into six areas. This section describes
what each area is for and why it exists, so the requirements can be read in
context rather than in isolation.

**CLI** — The commands plugin authors run day-to-day. `build` and `check` are
the workhorse operations; `init` and `migrate` are one-time setup. The CLI is
the only user-facing surface of shipyard.

**SCH** — The canonical source format. Plugin authors hand-edit two files:
`plugin.yaml` (plugin metadata and target list) and `hooks.yaml` (hook
behaviors in a runtime-neutral vocabulary). Everything else — skills, agents,
`.mcp.json` — is already in a format both targets accept unchanged and needs
no representation in the schema.

**BLD** — The projection engine. The core insight is that only manifests and
hook configs diverge by target; skill and agent files are identical. `BLD`
covers how shipyard reads canonical sources and writes the correct per-target
artifacts for each registered target.

**MKT** — Marketplace registry projection. The `claude-marketplace` repo lists
plugins available for install in Claude-format JSON. Copilot CLI reads a
different location and format. `MKT` covers deriving the Copilot registry from
the Claude one so both consumers can discover the same plugin set.

**DOC** — Documentation templating. Plugin docs reference install commands and
skill invocations that differ by target. `DOC` covers the preprocessor that
expands target-specific variables and groups adjacent target blocks into inline
tab controls, so a single doc page serves readers on either runtime.

**VAL** — Validation and CI. Generated files committed to git can drift when
canonical sources change without a subsequent `build`. `VAL` covers the check
command that catches drift and the contract that makes it a reliable CI gate.

## Requirements

### CLI — Command-line interface

- **[CLI-01]** When the user runs `shipyard init` in a plugin repo without canonical sources, the system shall scaffold the canonical source files and directory structure.
- **[CLI-02]** When the user runs `shipyard build`, the system shall regenerate all per-target outputs from canonical sources in place.
- **[CLI-03]** When the user runs `shipyard check`, the system shall verify all per-target outputs are consistent with their canonical sources, and exit non-zero on any discrepancy.
- **[CLI-04]** When the user runs `shipyard preview <target>`, the system shall install the plugin locally under the named target.
- **[CLI-05]** When the user runs `shipyard migrate` against an existing Claude-format plugin, the system shall produce canonical source files that describe the same plugin.
- **[CLI-06]** When the user runs `shipyard build-docs`, the system shall preprocess doc source files, expanding template variables and target-variant content blocks before the doc tool renders them.

### SCH — Canonical source schemas

- **[SCH-01]** `plugin.yaml` shall capture plugin identity (name, version, description) and declare which targets the plugin is built for.
- **[SCH-02]** `hooks.yaml` shall describe hook behaviors in a runtime-neutral vocabulary, with per-target mappings for event names and environment variables.
- **[SCH-03]** Skill files, agent files, and MCP server config shall be canonical sources shared across all targets without modification.

### BLD — Build pipeline

- **[BLD-01]** `shipyard build` shall produce a Claude-target manifest at `.claude-plugin/plugin.json`.
- **[BLD-02]** `shipyard build` shall produce a Copilot-target manifest at `.github/plugin/plugin.json`.
- **[BLD-03]** `shipyard build` shall produce a Claude-target hook config at `hooks/claude.json`, translating event names and environment variable references from the neutral vocabulary.
- **[BLD-04]** `shipyard build` shall produce a Copilot-target hook config at `hooks/copilot.json`, translating event names and environment variable references from the neutral vocabulary.
- **[BLD-05]** Generated files shall be identifiable as generated and reference their canonical source.

### MKT — Marketplace projection

- **[MKT-01]** `shipyard build --marketplace` shall produce a Copilot-format marketplace registry at `.github/plugin/marketplace.json` from `.claude-plugin/marketplace.json`.
- **[MKT-02]** The Copilot marketplace projection shall adapt field structure and plugin source references to the Copilot registry format.

### DOC — Documentation templating

- **[DOC-01]** The doc preprocessor shall support a standard template variable vocabulary covering plugin identity (`plugin.name`, `plugin.version`), marketplace coordinates (`marketplace.name`, `marketplace.repo`), target-specific install commands (`install.marketplace_add`, `install.plugin_install`), skill invocations (`skill.<name>`), and target identity (`target.name`, `target.cli`).
- **[DOC-02]** Authors shall be able to declare adjacent target-variant content blocks; the preprocessor shall group them into an inline tab control with one panel per declared target.
- **[DOC-03]** The tab control component shall synchronize target selection across all groups on the page, persist the selection across navigation, and honor a URL parameter to preset the selected target.
- **[DOC-04]** The default target selection shall be Claude.

### VAL — Validation and CI

- **[VAL-01]** `shipyard check` shall validate both build outputs and doc preprocessing outputs in a single invocation.
- **[VAL-02]** If `shipyard check` finds drift, it shall identify the affected outputs and exit non-zero.
