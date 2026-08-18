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

python3 -m shipyard generate --root ../some-plugin
```

Running `generate` against a real plugin checkout is worth doing before pushing a
generator change — `git diff` in that checkout then shows exactly what CI will
commit. Discard it afterwards; the projection belongs to that repo's own CI.

## Layout

```text
src/shipyard/cli.py       the entry point and subcommand table
src/shipyard/_common.py   root resolution and plugin.yml loading
src/shipyard/gen_*.py     one module per projection
src/shipyard/build_docs.py  renders skills/rules/guides/templates/references/SPEC.md/STATUS.md into docs/
src/shipyard/links.py     docsify's routing and heading-slug rules, for the link rewrite and the link check
tests/                    pytest suites
docs/                     shipyard's own docsify site, published by pages.yml
docs/cli-manifest.v1.json the CLI manifest's schema — published, so a consumer
                          can validate one without guessing at its shape
actions/                  the composite actions plugins call from their own jobs
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
flag that wasn't printed. And it's the one that needs the caller's own
toolchain, which is why the projection ships as an action in the caller's job
rather than a workflow that owns it: a CLI has to be built before it can be run.

**What plugins call is a public API.** `.github/workflows/{deploy-docs,
release}.yml` and `actions/{build-docs,project}` are called by every plugin via
`uses: chris-peterson/shipyard/<path>@v1`. Changing an input, output, or
permission changes their CI without them editing anything. (`pages.yml` and
`test.yml` are shipyard's own CI, not part of that surface.)

`v1` is a tag moved by hand, so a breaking change is coordinated rather than
versioned: every consumer is in one owner's hands, so the sweep converts all of
them and then moves the tag, with no release in between. That trade is the reason
there is one tag to reason about instead of a version per consumer — and the
reason a breaking change is a planned sweep, never a quiet edit.

## Conventions

- **Every generated artifact has exactly one writer, and it is CI.**
  `actions/project` runs the projectors on every push and commits the result to
  the branch, so a committed artifact matches its source at all times and the
  diff a reviewer approves is the change that lands. Nothing here gates on drift:
  a gate is what you build when the writer is a person with a local tool, and its
  failure message can only ever be *"run `generate` and commit"*.
- **`generate` is the single projection verb.** The per-artifact `gen-*` commands
  exist for targeted use; anything CI should project happens under `generate`, so
  there is one thing to call and one thing to keep in sync.
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
- **Python 3.10+, `pyyaml` the only runtime dependency**, `pytest` and
  `jsonschema` dev-only. The workflows and actions install `pyyaml` and run the
  CLI as `python3 -m shipyard` from a checkout, so nothing may depend on shipyard
  being pip-installed.
- **Hook descriptions come from `hooks.yml`**, not from a comment convention in
  the hook scripts. `gen-describe` reads them straight from the declaration.

## Glossary

- **Target plugin repo** — the checkout shipyard is operating on, selected by
  `--root` or the cwd. Never shipyard itself.
- **Projection** — a generated artifact derived from a declared source. Committed
  when a consumer reads it out of the repo (`plugin.json`, `hooks.json`,
  `marketplace.json`, a CLI manifest, compiled output a plugin ships); built at
  deploy otherwise (rendered `docs/`, the marketplace's data files).
- **Projection job** — the caller's job that runs its own build and then
  `actions/project`, which projects and pushes the result to the branch.
