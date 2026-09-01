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
python3 -m shipyard release                        # shipyard's own release; a plugin dispatches its Release workflow
```

Running `generate` against a real plugin checkout is worth doing before pushing a
generator change — `git diff` in that checkout then shows exactly what CI will
commit. Discard it afterwards; the projection belongs to that repo's own CI.

A plugin author has no shipyard checkout, so the same read from their side goes
through the console script this package declares:

```bash
uvx --from 'git+https://github.com/chris-peterson/shipyard@v2' shipyard generate
```

That's the answer to "the projection job is red and I can't see why", and it's
the form the plugin-facing docs give. It stays a *read* — CI is still the only
writer — so a change to `generate` that only makes sense when a human runs it is
a change aimed at the wrong caller.

## Layout

```text
src/shipyard/cli.py       the entry point and subcommand table
src/shipyard/_common.py   root resolution and plugin.yml loading
src/shipyard/gen_*.py     one module per projection
src/shipyard/_aggregate.py  the roster, the groups, and the artifact log a catalog declares
src/shipyard/changelog.py   CHANGELOG.md as the release's source of record, read and written
src/shipyard/build_docs.py  renders skills/rules/guides/templates/references/SPEC.md/STATUS.md into docs/
src/shipyard/links.py     docsify's routing and heading-slug rules, for the link rewrite and the link check
src/shipyard/validate.py  the gate over `claude plugin validate`: read its report, apply plugin.yml's acceptances
src/shipyard/cut.py       the local release driver: preflight, draft, preview, ship
src/shipyard/git.py       the git the driver needs, and nothing else
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
notify-marketplace,release}.yml` and `actions/{build-docs,project}` are called by
every plugin via `uses: chris-peterson/shipyard/<path>@<major>`. Changing an input, output, or
permission changes their CI without them editing anything. (`pages.yml` and
`test.yml` are shipyard's own CI, not part of that surface.)

So a breaking change here is always planned, never a quiet edit. It gets one of
two mechanisms, and the question that picks between them is whether the old and
new shapes have to **coexist**.

- **A mechanical break** (an input renamed, a permission added) doesn't. Every
  consumer is in one owner's hands, so the sweep converts all of them in one
  pass and then moves the current major's tag onto the result, with no release in
  between. That is why there is one tag to reason about per line, instead of a
  version per consumer.
- **A change to the shape or the mechanics** does. Converting a plugin is then a
  bet rather than a rename, so one plugin pilots the new shape while the rest go
  on running the old one. Coexistence is what a second major version is for.

While a pilot is running, `v2` is a **branch**. The pilot pins `@v2` and picks up
each shipyard push without editing its own workflow, and `v1` still points at the
old shape, so the unconverted repos keep releasing normally. Nothing is frozen,
which is what lets the soak run as long as it needs to. Once the pilot proves
out, delete the branch and create the `v2` **tag** at that commit: consumers'
`@v2` never changes, only the kind of ref behind it. That order matters, so the
repo never carries a branch and a tag of the same name at once.

The cost is two live lines for the length of the soak. A fix the old shape needs
in that window is a cherry-pick onto a `v1` branch and a re-cut tag.

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
- **`validate` reads; it never writes.** It runs `claude plugin validate` over the
  checkout and reports a verdict on the report. The ruleset stays the runtime's —
  restating those checks here would fork them, the same trap `gen-cli-manifest`
  avoids by invoking a CLI instead of parsing its source. What shipyard adds is
  the verdict: an error fails, and so does a warning `plugin.yml` hasn't accepted
  by name under `validate: accept:`, with a required `because`. An acceptance
  matching nothing in the report fails too — its reason has outlived the warning.
  The validator's version is pinned in `actions/project` because its ruleset
  reaches every plugin at once; moving the pin is the planned sweep.
- **A new CLI engine is a parser, not a special case.** `gen-cli-manifest`'s
  engines are keyed by name in `ENGINES` and all target the same manifest shape,
  so adding one (argparse, System.CommandLine) means writing a parser to that
  shape, not widening the shape to fit a framework. An engine that can walk its
  own parser should do that rather than parse prose; help text is the fallback
  for the ones that can't.
- **Missing required source is an error, not a default.** `load_plugin` raises on
  a missing `plugin.yml` rather than projecting from an empty dict — a generator
  that quietly writes a stub artifact produces a plugin that looks built and
  isn't. Malformed source is the same rule one step along: `_common.load_mapping`
  and `_common.block` reject a wrong-typed file or block by naming the file and
  the shape, because the alternative is an `AttributeError` from whichever
  projector dereferenced it first, read by someone with no shipyard checkout.
- **Every projector input comes from the target checkout.** No projection may take
  a fact about the plugin from anywhere else — an action input, an environment
  variable, the caller's workflow. That's what makes a local run reproduce CI's,
  and it's why resource paths are `plugin.yml`'s `docs: resources:` rather than an
  input on two actions.
- **Python 3.10+, `pyyaml` the only runtime dependency**, `pytest` and
  `jsonschema` dev-only. The workflows and actions install `pyyaml` and run the
  CLI as `python3 -m shipyard` from a checkout, so nothing on the CI path may
  depend on shipyard being pip-installed. The `[project.scripts]` entry point is
  for the local read above, and no projector may require it.
- **Hook descriptions come from `hooks.yml`**, not from a comment convention in
  the hook scripts. `gen-describe` reads them straight from the declaration.
- **A plugin releases through CI; shipyard releases itself locally.** Two drivers
  over one ordering, and which one a repo uses follows from what it is rather than
  from how far it has converted. A plugin writes its notes into `CHANGELOG.md`'s
  `## Unreleased`, commits them, and dispatches its own `release.yml` with a bump
  level; that calls the reusable `release.yml` here, whose `stage-release` step
  derives the version, retitles the section, commits, tags *that* commit,
  publishes from the section, and dispatches the marketplace rebuild. Every plugin
  in the suite is on this path, and it is the one the docs recommend.
  shipyard has no caller of its own to dispatch, so it releases from the
  operator's checkout with `cut.py` — the `release` verb — which answers the same
  questions before the first write instead of in a finished run. `cut.py` holds
  the one carve-out where a committed artifact is written outside CI, behind a
  preflight: a checkout whose `plugin.json` disagrees with `plugin.yml` is
  refused, because that is a commit the projection job still owes the branch and a
  release would land it after the tag.

## Glossary

- **Target plugin repo** — the checkout shipyard is operating on, selected by
  `--root` or the cwd. Never shipyard itself.
- **Projection** — a generated artifact derived from a declared source. Committed
  when a consumer reads it out of the repo (`plugin.json`, `hooks.json`,
  `marketplace.json`, a CLI manifest, compiled output a plugin ships); built at
  deploy otherwise (rendered `docs/`, the marketplace's data files).
- **Projection job** — the caller's job that runs its own build and then
  `actions/project`, which projects and pushes the result to the branch.
