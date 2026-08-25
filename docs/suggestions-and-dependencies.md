# Suggestions and dependencies

Two blocks in `plugin.yml` are read by Claude Code and by nothing else: a
`relevance` block, which asks Claude Code to offer the plugin to sessions whose
work matches it, and a `dependencies` list, which names the plugins it installs
alongside. Both reach Claude Code through generated manifests, so shipyard
projects them the same way it projects everything else.

What sets them apart is the feedback. A description with a typo in it is visible
on the catalog card; a signal name with a typo in it is *ignored at load time*,
and the plugin goes on making none of the suggestions it was written for, with
nothing anywhere to see. shipyard rejects those shapes at projection instead.

## Suggesting a plugin

`relevance` sits under the `marketplace:` block, because the marketplace entry is
where Claude Code reads it:

```yaml
marketplace:
  category: development
  homepage: https://chris-peterson.github.io/anchor/#/
  relevance:
    topic: Terraform            # fills "Working with Terraform?"; optional,
                                # defaults to the plugin name
    signals:                    # at least one; a block with none never fires
      cwd: [infra/**]           # working-directory globs
      cli: [terraform]          # exact command names run this session
      hosts: [registry.terraform.io]   # bare lowercase hostnames seen in URLs
      filesRead: ["**/*.tf"]    # globs over files read this session
      manifestDeps:             # a dependency inside a package manifest
        - file: '[/\\]package\.json$'
          pattern: '"stripe"\s*:'
```

A match surfaces the plugin three ways: a tip under the spinner, a one-line
notice before the first turn (`cwd` only), and a pin at the top of `/plugin`'s
Discover tab. Matching runs on the user's machine, and nothing about which signal
fired is reported anywhere.

Three semantics account for most mistaken blocks:

- **`filesRead` also covers files Claude *wrote* or edited**, and the `CLAUDE.md`
  memory files loaded automatically at session start. A glob over `**/CLAUDE.md`
  therefore fires in nearly every session.
- **`cli` sees only the leading command of a compound**, so `cd infra &&
  terraform plan` records `cd`.
- **`manifestDeps.file` is matched against an absolute path**, so it has to be
  end-anchored. A start-anchored pattern never matches anything.

Signals earn their keep by being narrow. A plugin surfaces at most once every
three sessions, so one that fires everywhere spends that on people who have no
use for it.

**Nothing surfaces until an administrator allowlists the marketplace.** The
marketplace name goes in `pluginSuggestionMarketplaces` in
[managed settings](https://code.claude.com/docs/en/managed-settings), with its
source declared alongside under `extraKnownMarketplaces` or
`strictKnownMarketplaces`. Requiring both is what stops an unvetted repo from
registering under an allowlisted name. Managed settings is endpoint-configured,
so a personal or project `settings.json` cannot turn suggestions on.

## Depending on another plugin

`dependencies` is a top-level key, and it projects into the plugin's own
`plugin.json`:

```yaml
dependencies:
  - audit-logger                # tracks whatever version its marketplace serves
  - name: secrets-vault
    version: "~2.1.0"           # an npm semver range
```

Installing the plugin installs these too, enabling it enables them, and
disabling one is refused while this plugin still needs it. Without a `version`, a
dependency follows its marketplace's latest, so an upstream release can change it
underneath you; a range holds it at a tested line until you widen it.

### These are not the doc site's dependency edges

`suite.dependencies` is a different field describing a different relationship,
and the two never mix:

| | `dependencies:` | `suite.dependencies:` |
|---|---|---|
| Read by | Claude Code | the doc site's graph |
| Projects into | `plugin.json` | `docs/deps.json` |
| On install | installs the dependency | nothing |
| If absent | the plugin is disabled | the plugin works, one path unavailable |
| Names | a plugin in a marketplace | anything, including tools the roster doesn't carry |

A preferred diff backend or an optional route tracker is a soft edge: the plugin
runs without it. Declaring one as a hard dependency would install a second plugin
on everyone who wanted the first.

### Depending across marketplaces

Claude Code refuses to auto-install a dependency from a marketplace other than
the one hosting the plugin. To allow it, the marketplace lists the target in its
`plugins.yml`:

```yaml
allowCrossMarketplaceDependenciesOn:
  - acme-shared
```

shipyard checks each plugin's `marketplace:` dependency field against that list
while generating the manifest, so a dependency that would fail at install fails
at projection instead.

### Version constraints need release tags shipyard does not write yet

Claude Code resolves a `version` range against tags named
`{plugin-name}--v{version}` on the repository hosting the dependency.
`shipyard release` tags `v{version}`. A constrained dependency on a
shipyard-released plugin therefore finds no matching tag and fails to install
with `no-matching-tag`. Until the release flow writes the prefixed tag,
declare dependencies without a `version`.

## What shipyard rejects, and what it doesn't

`claude plugin validate --strict` is worth running against a generated
marketplace manifest and catches a good deal on its own. The split:

| Shape | `claude plugin validate --strict` | shipyard |
|---|---|---|
| `signals` empty, missing, or over a cap | error | error |
| A hostname with a scheme, port, path, or uppercase | error | error |
| An uncompilable `manifestDeps` regex | error | error |
| A `topic` over 64 characters | error | error |
| A misspelled signal name | warning | error |
| An unknown key under `relevance` | warning | error |
| A `relevance` that isn't a mapping | warning | error |
| A repeated signal pattern | passes | error |
| A `version` that isn't a semver range | passes | error |
| A misspelled key on a dependency object | passes | error |
| A dependency on an unallowlisted marketplace | passes | error |
| A plugin depending on itself, or twice on one plugin | passes | error |

The warning rows are the ones worth the duplication: a warning is only as good
as the `--strict` run that reads it, and the shape it describes has no other
symptom.

`manifestDeps` regexes are compiled with Python's engine, which agrees with
JavaScript's on the anchors, classes, escapes, and quantifiers these patterns
use, and is stricter on JavaScript-only named-group syntax.
