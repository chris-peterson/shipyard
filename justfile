venv := justfile_directory() / ".venv"
shipyard := venv / "bin/shipyard"

# What this is, and every recipe there is
[private]
default:
    @echo ""
    @echo "  shipyard projects a plugin's sources into its generated files, and"
    @echo "  keeps a marketplace and its plugins wired together."
    @echo ""
    @echo "  New plugin?   just onboarding <name>       what it still needs to ship"
    @echo "  New token?    just dispatch-secret [name]  set the release dispatch token"
    @echo ""
    @just --list --unsorted --list-prefix '    ' --list-heading ''
    @echo ""
    @echo "  Every recipe runs this checkout's shipyard from .venv, which"
    @echo "  the first one to need it creates."

# What a plugin still needs before the marketplace ships it, with the fix for each gap
[group('marketplace')]
onboarding +names: _venv
    @{{shipyard}} onboarding {{names}}

# Set the marketplace dispatch token on every plugin, or on the ones named (prompts for it)
[group('marketplace')]
dispatch-secret *names: _venv
    @{{shipyard}} dispatch-secret {{names}}

# The plugins the marketplace lists, by name and repo
[group('marketplace')]
roster root='../claude-marketplace': _venv
    @{{shipyard}} roster --root {{quote(root)}}

# Project a plugin's sources the way CI does, then show what changed there
[group('a plugin checkout')]
check-generated root: _venv
    @{{shipyard}} generate --root {{quote(root)}}
    @git -C {{quote(root)}} --no-pager diff --stat

# Run Claude Code's plugin validator over a plugin checkout
[group('a plugin checkout')]
validate root: _venv
    @{{shipyard}} validate --root {{quote(root)}}

# Run any shipyard command: just cli --help
[group('a plugin checkout')]
cli *args: _venv
    @{{shipyard}} {{args}}

# Run shipyard's own test suite
[group('work on shipyard')]
test: _venv
    @{{venv}}/bin/pytest -q

# Serve shipyard's docs site at http://127.0.0.1:8000
[group('work on shipyard')]
docs: _venv
    @{{venv}}/bin/python -m http.server 8000 --directory docs

# Cut a shipyard release from this checkout
[group('work on shipyard')]
release *args: _venv
    @{{shipyard}} release {{args}}

# Create .venv with shipyard installed editable, plus its dev dependencies
[private]
_venv:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -x "{{shipyard}}" ] && [ -x "{{venv}}/bin/pytest" ] && exit 0
    echo "Creating .venv (one time)…" >&2
    if command -v uv >/dev/null; then
      uv venv --quiet "{{venv}}"
      uv pip install --quiet --python "{{venv}}/bin/python" -e ".[dev]"
    else
      python3 -m venv "{{venv}}"
      "{{venv}}/bin/pip" install --quiet -e ".[dev]"
    fi
