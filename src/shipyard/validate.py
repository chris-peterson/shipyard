"""Run Claude Code's own validator over the target checkout.

`claude plugin validate` reads the manifest a plugin ships and the frontmatter of
every skill, agent, and command beside it, and reports what Claude Code will
reject or silently ignore at load time. That ruleset belongs to the runtime and
moves with it, so shipyard runs the validator rather than restating its checks —
the same reason `gen-cli-manifest` invokes a CLI instead of parsing its source.

It needs no credentials, no config, and no network: it reads files off disk.

The verdict shipyard reports is stricter than the validator's own exit code and
looser than its `--strict`. An **error** always fails. A **warning** fails too,
unless the plugin's manifest accepts it by name:

    validate:
      accept:
        - warning: root
          because: >-
            CLAUDE.md at the root is this repo's own agent instructions, not
            shipped context. It is the only file Claude Code auto-loads.

`--strict` alone can't express that, and dropping to the default exit code lets
every warning through forever. Accepting one names it in the source of record,
with the reason beside it, where a reviewer sees it. Anything unnamed is new, and
new is what a gate is for.

An acceptance that no longer matches anything is an error as well. The reason it
records has outlived the warning it explains, and the next reader would take it
for a live exception.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

from . import _validate
from ._aggregate import MANIFEST, is_aggregate, load_manifest
from ._common import load_plugin, plugin_root

TOOL = "claude"
ARGS = ("plugin", "validate")

# The validator's report, line by line. `Validating <what>: <path>` opens a
# section; a `Found N errors:`/`Found N warnings:` header opens a block within
# it; `❯ <field>: <message>` is one finding in that block.
SECTION = "Validating "
ERROR_MARK = "✘"    # ✘
WARN_MARK = "⚠"     # ⚠
PASS_MARK = "✔"     # ✔
FINDING = "❯"       # ❯

# Every report ends in one of these. Requiring it is what separates "the
# validator looked and found nothing" from "something else ran": a first-run
# banner, a stub on PATH, a build that exits 0 having done nothing. Both read as
# a clean pass from the exit code alone.
VERDICTS = ("Validation passed", "Validation failed")

ACCEPT_FIELDS = ("warning", "because", "path")
REQUIRED = ("warning", "because")


class Finding:
    def __init__(self, kind: str, field: str, message: str, source: str):
        self.kind = kind
        self.field = field
        self.message = message
        self.source = source

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Finding({self.kind}, {self.field}, {self.source})"


def parse(output: str) -> list[Finding]:
    """The findings in one validator report.

    Nothing here guesses. A line that doesn't fit the grammar above is left
    alone, and `run` decides what an unrecognized report means — inferring a
    finding shipyard didn't actually read would make the gate report a verdict
    the validator never gave.
    """
    findings: list[Finding] = []
    source = ""
    kind = ""
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(SECTION):
            source = line.split(":", 1)[1].strip() if ":" in line else ""
            kind = ""
            continue
        if line.startswith(ERROR_MARK) or line.startswith(WARN_MARK):
            # `✘ Validation failed` is the trailer, not a block header.
            kind = ("error" if line.startswith(ERROR_MARK) else "warning") \
                if " Found " in line else ""
            continue
        if line.startswith(FINDING):
            body = line[len(FINDING):].strip()
            field, _, message = body.partition(":")
            findings.append(Finding(kind or "error", field.strip(),
                                    message.strip(), source))
            continue
        if line.startswith(PASS_MARK):
            kind = ""
            continue
        # A finding long enough to wrap continues on the next line.
        if findings and raw.startswith(" "):
            findings[-1].message = f"{findings[-1].message} {line}"
    return findings


def report(root: pathlib.Path) -> tuple[str, int]:
    """The validator's raw report and exit code for `root`."""
    if shutil.which(TOOL) is None:
        raise SystemExit(
            f"shipyard: {TOOL} is not on PATH, so the plugin cannot be "
            f"validated. Install Claude Code "
            f"(npm install -g @anthropic-ai/claude-code).")
    done = subprocess.run([TOOL, *ARGS, str(root)], capture_output=True,
                          text=True)
    return f"{done.stdout}{done.stderr}", done.returncode


def accept_errors(accept, where: str = "/validate/accept") -> list[str]:
    """Violations in one `validate: accept:` list, as messages naming the field.

    `because` is required. An acceptance is a standing exception to the gate, and
    one with no reason beside it is indistinguishable from a warning somebody
    silenced to get a build green.
    """
    if not isinstance(accept, list):
        return [f"{where} must be a list, but it is a {type(accept).__name__}"]

    errors: list[str] = []
    seen: list[tuple[str, str | None]] = []
    for i, rule in enumerate(accept):
        at = f"{where}/{i}"
        if not isinstance(rule, dict):
            errors.append(f"{at} must be a mapping with warning: and because:")
            continue
        for field in sorted(set(rule) - set(ACCEPT_FIELDS)):
            errors.append(f"{at}/{field} is not an acceptance field "
                          f"({', '.join(ACCEPT_FIELDS)})")
        for field in REQUIRED:
            value = rule.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{at}/{field} is required and must be a "
                              f"non-empty string")
        if "path" in rule and (not isinstance(rule["path"], str)
                               or not rule["path"].strip()):
            errors.append(f"{at}/path must be a path within the plugin")
        key = (rule.get("warning"), rule.get("path"))
        if key in seen:
            errors.append(f"{at} accepts {rule.get('warning')!r} a second time")
        seen.append(key)
    return errors


def _accepted(spec: dict, source: str) -> list[dict]:
    block = spec.get("validate")
    if block is None:
        return []
    if not isinstance(block, dict):
        raise SystemExit(f"shipyard: {source} `validate:` must be a mapping, "
                         f"but it is a {type(block).__name__}")
    accept = block.get("accept")
    if accept is None:
        return []
    _validate.raise_if(accept_errors(accept),
                       f"{source} declares acceptances shipyard cannot apply:")
    return accept


def _matches(rule: dict, finding: Finding) -> bool:
    if rule["warning"] != finding.field:
        return False
    where = rule.get("path")
    return where is None or finding.source.endswith(where)


def run(root: str | pathlib.Path | None = None) -> int:
    target = plugin_root(root)
    if is_aggregate(target):
        spec, source = load_manifest(target), MANIFEST
    else:
        spec, source = load_plugin(target), "plugin.yml"
    accept = _accepted(spec, source)

    output, code = report(target)
    # Flushed, because the verdict below leaves on stderr: unflushed, the report
    # it refers to lands after it in a CI log.
    print(output, end="" if output.endswith("\n") else "\n", flush=True)

    if not any(verdict in output for verdict in VERDICTS):
        raise SystemExit(
            f"shipyard: {TOOL} {' '.join(ARGS)} exited {code} without reaching "
            f"a verdict, so nothing was validated. The output is above.")

    findings = parse(output)
    if code != 0 and not any(f.kind == "error" for f in findings):
        raise SystemExit(
            f"shipyard: {TOOL} {' '.join(ARGS)} exited {code}, and its report "
            f"names no error shipyard could read. The report is above.")

    problems = [f"{f.source}: {f.field}: {f.message}"
                for f in findings if f.kind == "error"]
    for finding in findings:
        if finding.kind != "warning":
            continue
        if not any(_matches(rule, finding) for rule in accept):
            problems.append(
                f"{finding.source}: {finding.field}: {finding.message}\n"
                f"    Fix it, or accept it in {source} under "
                f"`validate: accept:` with the reason.")
    for rule in accept:
        if not any(_matches(rule, f) for f in findings if f.kind == "warning"):
            problems.append(
                f"{source} accepts the warning {rule['warning']!r}, which the "
                f"validator no longer reports. Drop the acceptance.")

    _validate.raise_if(problems, f"{target} does not pass plugin validation:")
    print(f"shipyard: {target.name} passes plugin validation"
          + (f" ({len(accept)} accepted warning"
             f"{'' if len(accept) == 1 else 's'})." if accept else "."))
    return 0
