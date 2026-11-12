---
name: add-plugin
description: Bootstrap a new plugin into a shipyard-built marketplace (such as bridge.ai), or report what an existing one still lacks. Use when adding, onboarding, bootstrapping, or listing a new plugin (e.g. "bootstrap acme-widget", "add acme-widget to the marketplace", "why isn't acme-widget in the catalog").
---

# Add a plugin to the marketplace

A plugin ships once its own repo, the marketplace (the aggregator holding
`plugins.yml`), the hub page the marketplace names under `hub:`, and the
plugin's GitHub settings all agree. `shipyard onboarding` reads every one of
them and prints each gap with its fix.

## 1. Check

```bash
uvx --from "${CLAUDE_PLUGIN_ROOT}/.." shipyard onboarding <name> [<name> ...]
```

It runs from anywhere beside the marketplace checkout: inside the marketplace,
inside a plugin checkout next to it, or with `--root <marketplace checkout>`.
Exit 0 means ready, 1 means gaps, 2 means a `gh` or auth error (stop and report
it). If the plugin's `plugin.yml` is missing, clone the plugin beside the
marketplace first.

## 2. Close the gaps

Work through the GAP rows in this order. Edit each repo's working tree; commit
and push only through `/anchor:commit` when the user asks.

| Gap | Where | How |
| --- | --- | --- |
| suite.group | plugin repo `plugin.yml` | one of the `groups:` keys the marketplace's `plugins.yml` declares |
| marketplace block | plugin repo `plugin.yml` | `marketplace:` with `category:` (one the marketplace already uses, unless the plugin needs a new one) and `homepage:` its docs site, placed after `validate:` |
| repo homepage | GitHub | the `gh repo edit` the fix line prints |
| Pages from Actions | GitHub | the `gh api` the fix line prints, before the first push to `main`: the docs deploy that push starts fails with "Get Pages site failed" until Pages exists |
| dispatch secret | GitHub | the user runs `shipyard dispatch-secret <name>` in their own terminal: it prompts silently for the PAT, checks it can dispatch to the marketplace, then sets it, so the value never passes through the session |
| on plugins.yml | marketplace `plugins.yml` | add the name next to the other plugins of its group; the list order is the catalog order |
| README section | marketplace `README.md` | sections follow the catalog: group order, then list order. Heading `### [<name>](<homepage>) — <group tag, lowercase>`, body from the plugin's `suite.what`, verified against its `skills/*/SKILL.md` |
| hub entry | the file `hub:` names | an entry in list order: `description` is `suite.gloss`, `icon` the plugin's `favicon.svg`, `languages` from `gh api repos/<owner>/<name>/languages` (mark mostly-Markdown repos `source: manual`) |
| released | plugin repo | a release needs `CHANGELOG.md`'s `## Unreleased` written and the dispatch secret set; hand off to `/anchor:release` with a minor bump. A new plugin's `plugin.yml` starts at `version: 0.0.1`, never `0.0.0`, so that first release makes it 0.1.0 |

The release is last because its workflow dispatches to the marketplace with the
secret, and the catalog rebuild it triggers only lists plugins on `plugins.yml`.

## 3. Re-check

Run the check again and report its output as-is. Gaps left for the user (the
secret, the release) stay listed with their fix line.
