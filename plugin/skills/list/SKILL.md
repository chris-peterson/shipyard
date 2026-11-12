---
name: list
description: List what the bridge.ai marketplace ships (each plugin's category, version, description, and how many skills, rules, hooks, and commands it has) from the live catalog. Use when asked what's in bridge.ai, which plugins exist, which have a CLI, or how big a plugin is (e.g. "what plugins are in bridge.ai", "list the marketplace", "which bridge.ai plugins are documentation plugins").
---

# List bridge.ai

```bash
uvx --from "${CLAUDE_PLUGIN_ROOT}/.." shipyard list --json
```

This reads the catalog the marketplace's site publishes
(`https://chris-peterson.github.io/claude-marketplace/catalog.json`), so the
answer is what users can install right now. Each entry has a `type`
(`marketplace` or `plugin`), `name`, `category`, `version`, `description`,
`cli`, `counts`, and `components` (the names behind the counts).

- Narrow it with `--type plugin`.
- To read a marketplace checkout that hasn't deployed yet, pass
  `--root <marketplace checkout>`; it builds the same catalog from the
  sibling plugin checkouts.
- An HTTP 404 means the site predates `catalog.json`. Say so, and offer
  the `--root` read if a checkout is nearby.

Answer the question asked from the JSON. A table is the right shape only when
the user asked for the list itself; `shipyard list` without `--json` prints one
for a person at a terminal.
