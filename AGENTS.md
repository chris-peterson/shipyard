# shipyard

Shared build tooling for chris-peterson's Claude Code plugins. Each plugin repo
used to carry its own copy of the same generators; shipyard holds that logic once
and the plugins call it from CI. How it works, and a before/after walk-through of
converting a plugin, are on the docs site
(https://chris-peterson.github.io/shipyard); this file is for working on shipyard
itself.

**shipyard is not a plugin.** It's a Python package that runs *against* a target
plugin repo — the one whose sources it projects. Every command resolves that
repo's root the same way: an explicit `--root`, else the current directory (which
is how CI runs it, from the plugin checkout). Root is never derived from
shipyard's own file location; the per-plugin scripts it replaced did that, and
it's the mistake to avoid re-introducing.

## Commands

```bash
pip install -e ".[dev]"
pytest

python3 -m shipyard generate --root ../some-plugin --dry-run
```

`--dry-run` is worth running against a real plugin checkout before pushing a
generator change: it prints the diff the next write would apply, without touching
the tree.

## Layout

```text
src/shipyard/cli.py       the entry point and subcommand table
src/shipyard/_common.py   root resolution, plugin.yml loading, the diff helper
src/shipyard/gen_*.py     one module per projection
src/shipyard/build_docs.py  renders skills/rules/guides/templates/references/SPEC.md/STATUS.md into docs/
src/shipyard/links.py     docsify's routing and heading-slug rules, for the link rewrite and the link check
tests/                    pytest suites
docs/                     shipyard's own docsify site, published by pages.yml
docs/cli-manifest.v1.json the CLI manifest's schema — published, so a consumer
                          can validate one without guessing at its shape
.github/workflows/        the reusable workflows plugins call, plus shipyard's own CI
```

## The two contracts

Both of these reach outside this repo, so a change to either lands in every
plugin at once.

**Source → projection.** A plugin's source is the source of record — `plugin.yml`
for metadata and presentation, `hooks/hooks.yml` for hook registrations, and the
skills/rules/hooks themselves for their own descriptions. shipyard projects those
into generated, committed artifacts (`.claude-plugin/plugin.json`,
`hooks/hooks.json`, `docs/plugin-docs.json`, `plugin.yml`'s `suite.describe`, most
of `docs/`). A generator that reads something a plugin hand-maintains, rather than
its declared source, breaks the split the whole suite depends on.

`gen-cli-manifest` is the one whose source of record is a *running program*: it
invokes the CLI declared in `plugin.yml`'s `cli:` block and records the grammar
its help documents. Two consequences shape the code. The manifest asserts what
the CLI documents rather than what it accepts, so a parser must never infer a
flag that wasn't printed. And it's the one artifact whose drift is *gated*
(`--check`) rather than surfaced, because a CLI's grammar is a public contract
and a rename has to appear in the diff of the change that made it — which is
also why it is left out of `generate --dry-run`, where a preview job has no
toolchain to build the CLI it would have to run.

**The reusable workflows are a public API.** `.github/workflows/{deploy-docs,
preview,release}.yml` are called by every plugin via `uses:
chris-peterson/shipyard/.github/workflows/<name>.yml@v1`. Changing an input,
output, or permission changes their CI without them editing anything. The `v1` tag
is what they pin, so a breaking change needs a new tag rather than a moved one.
(`pages.yml` and `test.yml` are shipyard's own CI, not part of that surface.)

## Conventions

- **Preview never fails on drift**, the CLI manifest above excepted. Between
  releases the committed artifacts are *expected* to trail their source — the release workflow regenerates and commits
  them back. `generate --dry-run` fails only when the source itself is malformed
  or missing required input; otherwise it posts the pending diff to the job
  summary so a reviewer sees what release will apply. Making preview gate on
  drift would fail every ordinary PR.
- **`generate` is the single projection verb.** The per-artifact `gen-*` commands
  exist for targeted use; anything that should happen at release happens under
  `generate`, so there is one thing to call and one thing to keep in sync.
- **A new CLI engine is a parser, not a special case.** `gen-cli-manifest`'s
  engines are keyed by name in `ENGINES` and all target the same manifest shape,
  so adding one (argparse, System.CommandLine) means writing a parser to that
  shape, not widening the shape to fit a framework. An engine that can walk its
  own parser should do that rather than parse prose; help text is the fallback
  for the ones that can't.
- **Missing required source is an error, not a default.** `load_plugin` raises on
  a missing `plugin.yml` rather than projecting from an empty dict — a generator
  that quietly writes a stub artifact produces a plugin that looks built and
  isn't.
- **Python 3.10+, `pyyaml` the only runtime dependency**, `pytest` dev-only. The
  reusable workflows `pip install pyyaml` and run the CLI as `python3 -m shipyard`
  from a checkout, so nothing may depend on shipyard being pip-installed.
- **Hook descriptions come from `hooks.yml`**, not from a comment convention in
  the hook scripts. `gen-describe` reads them straight from the declaration.

## Glossary

- **Target plugin repo** — the checkout shipyard is operating on, selected by
  `--root` or the cwd. Never shipyard itself.
- **Projection** — a generated, committed artifact derived from a declared
  source. Stale between releases by design.
- **Preview** — `generate --dry-run`: validate the source, diff the pending
  projection, write nothing, and don't fail on drift.
- **Wrapper** — the `scripts/shipyard` shim a plugin repo carries to fetch and
  invoke the CLI, pinned to the same ref as its workflow callers.
