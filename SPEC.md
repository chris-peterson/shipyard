# shipyard — Specification

A CLI tool that reads a neutral `plugin.yaml` canonical source and generates
target-specific manifests and hook configs in place, so a single plugin repo
can be consumed by Claude Code and GitHub Copilot CLI without maintaining
parallel hand-authored files.

Beyond projection, shipyard scaffolds and enforces the conventions that keep a
plugin healthy over its lifetime — among them a freshness hook, completion sync,
a single version source of truth, and a stable state location. Several of these
guard against a recurring, silent drift: a wrapper left pointing at an old build
after an upgrade, an embedded completion block that fell out of sync with the
installed copy, a second manifest bumped independently. shipyard's job is to lay
these conventions down at `init` and catch their drift at `check`.

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
- **PATH wrapper** — an executable installed on the user's `PATH` by the CLI's `install-cli` subcommand that forwards to the plugin's CLI; it records the install location, so a plugin upgrade can leave it pointing at the old build
- **wrapper skill** — the skill that serves as the plugin's conversational entry point to its CLI
- **ambient rule** — guidance emitted into session context by a `SessionStart` hook (as `rules/*.md`), in force for the whole session rather than only inside a skill
- **sextant project** — a repo whose requirements live in a `SPEC.md`, optionally tracked against a maintainer-facing `STATUS.md` coverage ledger, under the sextant spec-driven toolkit

## Feature groups

The requirements below are organized into the areas described here. This
section describes what each area is for and why it exists, so the requirements
can be read in context rather than in isolation.

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
tab controls, so a single doc page serves readers on either runtime. It also
covers surfacing a sextant project's requirements as a generated, de-emphasized
page — filtered to what's actually built when a `STATUS.md` is present, since
the coverage ledger itself is maintainer-facing.

**VAL** — Validation and CI. Generated files committed to git can drift when
canonical sources change without a subsequent `build`. `VAL` covers the check
command that catches drift and the contract that makes it a reliable CI gate.

**SHP** — The shape of the scaffolded CLI itself: a single executable file, a
one-line slash shim, a uniform help/exit contract, and loud failures. These are
the conventions that make one operation callable identically from a skill, a
hook, a slash command, or the shell. It also covers the wrapper skill that
serves as the plugin's conversational entry point when it ships a CLI.

**OUT** — Interactive vs. non-interactive output. A CLI runs both at a terminal
and inside pipes, redirects, `watch(1)`, and hook contexts. `OUT` covers
resolving color by an explicit precedence so piped output stays clean yet
overridable, and reserving live views for a real TTY while a one-shot command
remains the scriptable surface.

**FRS** — The freshness hook. A PATH-installed wrapper is a snapshot of where
it was installed, so a plugin upgrade leaves it pointing at the old build. `FRS`
covers the `SessionStart` hook that surfaces this drift for every consumer of
the CLI, not just users who happen to invoke a particular skill.

**CMP** — Completion sync. Shell completion embedded in the CLI source drifts
from the installed copy whenever a subcommand or flag changes without a
reinstall. `CMP` covers embedding completion in the CLI, folding its install
into `install-cli`, and a hook that flags the embedded-vs-installed gap when the
CLI source is edited.

**VER** — Version source of truth. Claude Code caches plugins by version
string, so a duplicated or stale version field silently suppresses updates.
`VER` covers reading the version from one manifest at runtime and freezing any
auxiliary manifest a build toolchain forces.

**STA** — State location. State written inside the plugin install directory is
clobbered on upgrade, and state keyed off an env var only hooks receive splits
across invocation contexts. `STA` covers where plugin state lives and how its
location is resolved.

**DST** — Distribution. The artifacts a consumer needs to discover and apply an
update: a changelog and a README that explains the update path on marketplaces
where auto-update is off by default.

**PUB** — Multi-publishing. A plugin is installable by cloning its repo directly
or through a marketplace, and the same plugin can be listed in several
marketplaces — sometimes advertised under a different name. `PUB` covers keeping
the plugin's canonical identity stable while each marketplace owns its own entry
and branding, and preserving those entries through projection. Distinct from
`MKT`, which projects one registry between target formats; `PUB` is about one
plugin reaching many registries.

**AMB** — Ambient rules. Some plugin guidance must hold even when the user never
invokes a skill — a launch contract, an etiquette rule about ad-hoc operations.
`AMB` covers delivering that guidance as `rules/*.md` emitted by a `SessionStart`
hook, so it is in context for the whole session rather than only after a skill
fires, and the test for which guidance belongs there versus in a skill.

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
- **[DOC-05]** Where the project is a sextant project, `shipyard build-docs` shall generate a docs page presenting the requirements collected from its `SPEC.md`.
- **[DOC-06]** Where a `STATUS.md` accompanies the spec, the generated page shall present only met requirements, omitting unmet and future (FUT) requirements; where no `STATUS.md` is present, it shall present all requirements.
- **[DOC-07]** The generated page shall present requirement text only, not the coverage status, which is maintainer-facing.
- **[DOC-08]** The generated requirements page shall be de-emphasized in the docs navigation — placed low in the sidebar and table of contents rather than in a primary position.

### VAL — Validation and CI

- **[VAL-01]** `shipyard check` shall validate both build outputs and doc preprocessing outputs in a single invocation.
- **[VAL-02]** If `shipyard check` finds drift, it shall identify the affected outputs and exit non-zero.

### SHP — CLI shape

- **[SHP-01]** When the user runs `shipyard init`, the system shall scaffold a single-file CLI at `scripts/<name>` and a one-line `commands/<name>.md` slash shim that forwards its arguments to the CLI.
- **[SHP-02]** The scaffolded CLI shall resolve its plugin root from `CLAUDE_PLUGIN_ROOT` or its own file location, so it runs both inside the plugin install directory and from a clone.
- **[SHP-03]** The scaffolded CLI shall print usage to stdout and exit zero for `--help`, `-h`, and `help`, and print usage to stderr and exit non-zero for no-args and unrecognized commands.
- **[SHP-04]** Where a plugin ships a CLI, `shipyard init` shall scaffold a wrapper skill as the plugin's conversational entry point — the counterpart to the CLI's `--help` surface for discoverability; the skill shall invoke CLI subcommands for deterministic operations rather than reproducing the CLI's surface.
- **[SHP-05]** If a CLI operation fails, then the CLI shall write an actionable message to stderr and exit non-zero rather than falling back to a degraded result.

### OUT — Interactive output and color

- **[OUT-01]** The scaffolded CLI shall resolve color output by precedence — a `--color=auto|always|never` flag first, then `NO_COLOR` (force off) and `FORCE_COLOR`/`CLICOLOR_FORCE` (force on), then whether stdout is a TTY — so redirected and piped output is clean by default yet overridable.
- **[OUT-02]** Where the CLI provides a live or interactive view (e.g. a `watch` subcommand), it shall require a TTY and own the terminal, leaving a one-shot, non-interactive command as the scriptable surface.

### FRS — CLI freshness

- **[FRS-01]** When the user runs `shipyard init`, the system shall scaffold a `SessionStart` hook that compares the installed CLI's reported version against `.claude-plugin/plugin.json` and, on a mismatch, tells the user to re-run `install-cli`, without blocking the session.
- **[FRS-02]** When the user runs `shipyard init`, the system shall scaffold the CLI's `install-cli` subcommand to install a PATH wrapper rather than define a shell alias, so the freshness hook can detect the installed version from a non-interactive shell.

### CMP — Completion sync

- **[CMP-01]** The scaffolded CLI shall embed its shell completion as a constant and install it via a `completions` subcommand, with no separate completion file maintained in the repo.
- **[CMP-02]** Where the scaffolded CLI exposes an `install-cli` subcommand, it shall install the shell completion as part of that same command through a shared helper, so one command leaves completion working.
- **[CMP-03]** When the user runs `shipyard init`, the system shall scaffold a `PostToolUse` hook that, when the CLI source file is edited, reminds the developer to reconcile the embedded completion block and reinstall it.

### VER — Version source of truth

- **[VER-01]** The scaffolded CLI's version flag shall read the version from `.claude-plugin/plugin.json` at runtime, with no version constant duplicated in code.
- **[VER-02]** `.claude-plugin/plugin.json` `version` shall be the single source of truth for the plugin version.
- **[VER-03]** Where a build toolchain requires an auxiliary manifest (`package.json`, `Cargo.toml`, `pyproject.toml`), `shipyard init` shall freeze its version at a private stub.
- **[VER-04]** `shipyard check` shall flag any auxiliary manifest whose version diverges from `.claude-plugin/plugin.json`.

### STA — State location

- **[STA-01]** The scaffolded CLI shall store state under `~/.<name>/` or `~/.claude/plugins/data/<name>/`, never inside the plugin install directory.
- **[STA-02]** The scaffolded CLI shall derive its state directory from the resolved plugin root, so hook, slash-command, and shell invocations converge on one location rather than depending on `CLAUDE_PLUGIN_DATA` being set.

### DST — Distribution and updates

- **[DST-01]** When the user runs `shipyard init`, the system shall scaffold a `CHANGELOG.md` and a README "Updating" section documenting that third-party marketplaces have auto-update off by default.

### PUB — Multi-publishing

- **[PUB-01]** A plugin shall be installable both by direct `git clone` of its repository and via a marketplace, with no canonical-source changes between the two.
- **[PUB-02]** The same plugin source shall be registrable in more than one marketplace, including under a different advertised name per marketplace, without changes to the plugin's canonical `plugin.yaml` identity.
- **[PUB-03]** When shipyard projects a marketplace registry to another target, it shall preserve each entry's advertised name and source, so a rebranded entry keeps its rebranding across targets.

### AMB — Ambient rules

- **[AMB-01]** When the user runs `shipyard init`, the system shall scaffold a `SessionStart` hook that emits the plugin's ambient rules (`rules/*.md`) into session context.
- **[AMB-02]** Domain guidance that must hold between skill invocations shall be expressed as ambient rules; procedure and entry-point-scoped guidance shall remain in skills.
