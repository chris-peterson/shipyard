# How it works

Two halves: the **generators** that project source into artifacts, and the **reusable CI** that runs them in each plugin.

## Two kinds of target

shipyard runs against a checked-out repo, and tells what kind it is from the manifest at its root: a **plugin** carries `plugin.yml`, an **aggregator** carries `plugins.yml`. `generate` dispatches on that, so there is one projection verb rather than two command families to keep in sync.

The distinction is about who owns which fact. A plugin owns everything about itself. An aggregator owns only the roster — which plugins it presents, and in what order — and reads the rest off the plugins themselves.

## Generators

Each generator reads a plugin's canonical source and writes a committed artifact.

- **`gen-plugin-json`** — projects the packaging fields of `plugin.yml` into `.claude-plugin/plugin.json` (the file Claude Code reads at install), including `homepage` from the `marketplace:` block.
- **`gen-describe`** — the interesting one. It derives a one-line description for every artifact from the artifact's *own* source, and syncs them into `plugin.yml` between generated markers:

  | Artifact | Description comes from |
  |---|---|
  | skill | the first sentence of its `SKILL.md` `description:` |
  | command | the first sentence of its command `description:` |
  | rule | the rule file's first `#` heading |
  | hook | its `description:` in `hooks/hooks.yml` + the event/matcher it's wired to |

  Hooks are declared in `hooks/hooks.yml` — the source of record, a flat, commentable list of `{event, matcher?, command, description}` — which **`gen-hooks-json`** projects into the `hooks/hooks.json` Claude Code reads (the same source → generated split as `plugin.yml` → `plugin.json`). `gen-describe` reads each hook's `description:` straight from `hooks.yml`, so the hook scripts carry no `# DOCUMENTATION:` line.

- **`build-docs`** — renders `skills/`, `rules/`, `guides/`, `templates/`, and `SPEC.md` into `docs/`, plus `plugin-docs.json`. When `plugin.yml` carries a `docs:` block it also projects the docsify `docs/index.html` (title/description from the packaging fields; `code_languages` and `mermaid` from `docs:`; the session player when a `suite:` is present) — so the bootstrap lives here once instead of a hand-copied file per plugin. The plugin's docsify site serves the result; nothing is hand-maintained twice.

  Only `docs/` is published, so a page's `<img src="hero.svg">` resolves only if that file is in the artifact. **Resource paths** put it there: each path the caller names is copied in, with its directory flattened to the docs root, so `assets/hero.svg` is reachable as `hero.svg` — the same placement each plugin's own `cp assets/* docs/` step gave it before shipyard replaced that step. Name them on the build's `resources` input; `assets` applies when you name nothing.

  `build-docs` then resolves every local file reference the rendered pages make against the tree as it will ship, and fails on one it can't. That gate is the point: a reference to a file that isn't published costs nothing at build time and shows up only as a blank space on the live page, which is how one plugin's homepage hero stayed missing for a month behind a green deploy. References inside code fences and inline spans are prose, not references, so a guide that *documents* markdown isn't punished for it.

The marker block `gen-describe` writes means editing is one-directional — you change the source, run the generator, and the committed copy follows:

```mermaid
%%{ init: { 'look': 'handDrawn' } }%%
flowchart LR
  edit["edit a SKILL.md / hook / rule"] --> gen["shipyard gen-describe"]
  gen --> yml["plugin.yml suite.describe"]
  yml --> hub["bridge.ai tooltips"]
  yml --> site["plugin docs preview"]
```

## Aggregate generators

An aggregator — a marketplace, a catalog site — used to hand-maintain a second copy of every plugin's description, author, category, and homepage. That copy is a projection of facts the plugins already declare, so it drifts: a description reworded in the plugin's own repo has no path to the marketplace except somebody editing it there too.

`plugins.yml` removes the copy. It declares only what the aggregator owns, and the plugins supply the rest:

```mermaid
%%{ init: { 'look': 'handDrawn' } }%%
flowchart LR
  roster["plugins.yml"] --> sync["sync: clone the plugins"]
  sync --> spokes["each plugin.yml"]
  roster --> mp["marketplace.json"]
  spokes --> mp
  log["artifacts log"] --> js["docs/plugins.js"]
  spokes --> js
  spokes --> deps["docs/deps.json"]
```

- **`gen-marketplace-json`** — the roster plus each plugin's `plugin.yml` become the `marketplace.json` Claude Code reads at `marketplace add`. Generated and committed, the same split as `plugin.yml` → `plugin.json` one level up.
- **`gen-plugins-js`** and **`gen-deps-json`** — the doc site's catalog data and dependency graph, projected from the plugins' `suite:` blocks. Render targets, regenerated on every docs build.
- **`roster`** — prints the declared plugins as `name<TAB>url` pairs.

Two design points carry most of the weight:

**`source:` is a URL template, not a per-entry field.** The aggregator's sync step needs to know what to clone *before* any plugin is on disk. Resolving `https://github.com/{owner}/{name}.git` from the roster alone keeps `roster` readable with an empty workspace — which is what lets `marketplace.json` be purely downstream rather than doubling as the list of things to fetch.

**A rostered plugin with no `plugin.yml` is a hard error.** The alternative — skipping it, or falling back to a stale local copy — would publish an incomplete catalog that looks complete. Unsynced plugins fail the build instead.

The artifact log is the one derived input: a rolling record of each plugin's named skills, rules, and hooks that the aggregator's recorder writes from the plugins' git state. shipyard reads it when `plugins.yml` declares an `artifacts:` path, replaying its `+`/`-` tokens to get the current member set, so the catalog can't list a skill a plugin no longer ships. Component names are never declared, only derived.

A plugin may declare a dependency on something the roster doesn't carry — an optional backend the marketplace doesn't ship. Those edges survive into `deps.json` while `nodes` stays the roster; that gap is what lets the doc site's graph draw an outside plugin differently from a catalog one.

## The wrapper: fetch-and-run, no install

`scripts/shipyard` in each plugin keeps a cached checkout of shipyard and runs it in place — no package to publish or pin a version of the interpreter against.

```mermaid
%%{ init: { 'look': 'handDrawn' } }%%
sequenceDiagram
  participant J as just / pre-commit
  participant W as scripts/shipyard
  participant C as ~/.cache/shipyard
  J->>W: shipyard generate --dry-run
  W->>C: clone or fast-forward @main
  W->>W: PYTHONPATH=cache/src python3 -m shipyard generate --dry-run
  W-->>J: exit 0 (+ pending-projection diff) / non-zero (malformed source)
```

## The preview gate

A plugin's CI calls shipyard's reusable `preview` workflow on every push and pull request. It fetches shipyard, then dry-runs the projection: it validates that `plugin.yml` and `hooks.yml` are well-formed enough to project, and posts a diff of what the next release will apply to the committed artifacts. It fails only when the source itself is malformed. The committed artifacts trailing their source is expected between releases — the release workflow regenerates and commits them back — so that gap is surfaced, not gated.

## The release flow

Publishing a GitHub release on a plugin fires its `release.yml`, a one-line caller of shipyard's reusable release workflow. shipyard does the rest and hands off to the marketplace.

```mermaid
%%{ init: { 'look': 'handDrawn' } }%%
sequenceDiagram
  actor You
  participant GH as plugin repo
  participant SY as shipyard release.yml
  participant MP as bridge.ai marketplace
  You->>GH: publish release vX.Y.Z
  GH->>SY: uses shipyard release workflow
  SY->>SY: resync describe, regenerate plugin.json
  SY->>SY: write version, proxy notes to CHANGELOG
  SY->>GH: commit + push to main
  SY->>MP: repository_dispatch (plugin-released)
  MP->>MP: rebuild the catalog from every plugin.yml
```

Nothing here is plugin-specific — the plugin name comes from the repository — so one reusable workflow drives every plugin.

What the person (or agent) publishing the release is responsible for, and what to leave to CI, is in **[Cutting a release](releasing.md)**.
