"""shipyard — consistent build tooling for chris-peterson's Claude Code plugins.

Projects each plugin repo's canonical sources (plugin.yml + skills/rules/hooks)
into their generated artifacts (.claude-plugin/plugin.json, docs/, suite.json),
so the per-plugin build logic lives here once instead of copied into every repo.
"""
__version__ = "0.0.0"
