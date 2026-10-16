"""Bound module size, and ratchet the files already over it downward.

Ruff has no module-length rule, so this is what stops a file growing by
accumulating small functions. ``RULES`` lists what is checked.

    uv run python -m tools.lint.check_module_size            # gate
    uv run python -m tools.lint.check_module_size --report   # every file, with headroom
    uv run python -m tools.lint.check_module_size --update   # re-record the baseline

A file over a cap needs an entry in the baseline beside this script. ``--update``
writes one, and will not raise a number or a total that already exists: the way
out of a failure is a smaller file, not a bigger allowance.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import subprocess
import sys
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tools.lint.source_trees import physical_lines, python_files

#: ``backend/``: this file sits two directories below it.
ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().parent / "module_size_baseline.json"

#: Code lines: blanks, comment lines, and docstrings excluded. A raw line cap
#: would tax a file for its documentation.
LINE_CAP = 400

#: Declared public surface. A module offering this many names is a bag of
#: functions whatever its length.
PUBLIC_CAP = 30

#: Rule -> (what it measures, the ``Metrics`` field holding it, its cap).
#: MS002 is unused, matching the reference implementation this was ported from.
RULES = {
    "MS001": (f"over {LINE_CAP} code lines", "lines", LINE_CAP),
    "MS003": (f"over {PUBLIC_CAP} public names", "public", PUBLIC_CAP),
}

Baseline = dict[str, dict[str, int]]


@dataclass(frozen=True)
class Metrics:
    """One module's measured size, and the allowance its baseline entry buys it."""

    path: str
    lines: int
    public: int
    allowed: dict[str, int]
    error: str = ""

    def actual(self, rule: str) -> int:
        return int(getattr(self, RULES[rule][1]))

    @property
    def violations(self) -> list[str]:
        rules = rules_for(self.path)
        if self.error:
            return sorted(rules)[:1]
        return [
            rule for rule in sorted(rules) if self.actual(rule) > self.allowed[rule]
        ]

    def render(self, rule: str) -> str:
        if self.error:
            return f"{self.path}: unreadable: {self.error}"
        return (
            f"{self.path}: {rule} {RULES[rule][0]}: "
            f"{self.actual(rule)}, allowed {self.allowed[rule]}"
        )


def rules_for(rel: str) -> frozenset[str]:
    """The rules that apply to a file.

    A test module's public surface is its test classes, so counting them
    measures nothing.
    """
    if rel.startswith("tests/"):
        return frozenset(RULES) - {"MS003"}
    return frozenset(RULES)


def _docstring_lines(tree: ast.Module) -> set[int]:
    owners = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    spans: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, owners) or not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if isinstance(first.value.value, str):
            end = first.value.end_lineno or first.value.lineno
            spans.update(range(first.value.lineno, end + 1))
    return spans


def _comment_lines(source: str) -> set[int]:
    """Whole-line comments only; a trailing comment sits on a line of code."""
    lines = physical_lines(source)
    found: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            lineno = token.start[0]
            if token.type == tokenize.COMMENT and lines[lineno - 1].lstrip().startswith(
                "#"
            ):
                found.add(lineno)
    except (tokenize.TokenError, SyntaxError):
        return found
    return found


def _declared_all(tree: ast.Module) -> list[str] | None:
    """The names in a literal top-level ``__all__``, or None when there is not one."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        if isinstance(node.value, ast.List | ast.Tuple):
            return [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    return None


def _public_symbols(tree: ast.Module, rel: str) -> int:
    """How many public names the module offers.

    A declared ``__all__`` is the answer where there is one. Otherwise it is what
    the module defines, plus, in a package ``__init__``, what it re-exports.
    """
    declared = _declared_all(tree)
    if declared is not None:
        return sum(not name.startswith("_") for name in declared)

    count = 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            count += not node.name.startswith("_")
        elif isinstance(node, ast.Assign):
            count += sum(
                not t.id.startswith("_")
                for t in node.targets
                if isinstance(t, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            count += not node.target.id.startswith("_")
        elif isinstance(node, ast.ImportFrom) and rel.endswith("/__init__.py"):
            count += sum(
                not (alias.asname or alias.name).startswith("_")
                for alias in node.names
                if alias.name != "*"
            )
    return count


def measure(source: str, rel: str, baseline: Baseline) -> Metrics:
    """Measure one module against its baseline entry, or against the caps.

    Source that will not parse is reported as a failure, never raised: one
    unreadable file must not take the whole gate down with it.
    """
    recorded = baseline.get(rel, {})
    allowed = {
        rule: max(recorded.get(field, 0), cap)
        for rule, (_, field, cap) in RULES.items()
    }
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as error:
        return Metrics(rel, 0, 0, allowed, error=f"{type(error).__name__}: {error}")

    skip = _docstring_lines(tree) | _comment_lines(source)
    numbered = enumerate(physical_lines(source), 1)
    return Metrics(
        path=rel,
        lines=sum(
            1 for number, text in numbered if number not in skip and text.strip()
        ),
        public=_public_symbols(tree, rel),
        allowed=allowed,
    )


def load_baseline() -> Baseline:
    """The recorded allowances. A corrupt file is a failure with a name, not a traceback."""
    if not BASELINE.exists():
        return {}
    try:
        return dict(json.loads(BASELINE.read_text(encoding="utf-8"))["modules"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SystemExit(f"{BASELINE.name} is unreadable: {error}") from error


def scan_repo(baseline: Baseline | None = None) -> list[Metrics]:
    """Measure every scanned file, largest first."""
    recorded = load_baseline() if baseline is None else baseline
    measured = [
        measure(
            path.read_text(encoding="utf-8-sig", errors="replace"),
            path.relative_to(ROOT).as_posix(),
            recorded,
        )
        for path in python_files(ROOT)
    ]
    return sorted(measured, key=lambda m: (-m.lines, m.path))


def gating(measured: Iterable[Metrics]) -> list[tuple[Metrics, str]]:
    """Every (file, rule) over its allowance."""
    return [(metric, rule) for metric in measured for rule in metric.violations]


def entry_for(metric: Metrics) -> dict[str, int]:
    """What the baseline should record for a file: every applicable rule it is over."""
    if metric.error:
        return {}
    rules = rules_for(metric.path)
    return {
        field: metric.actual(rule)
        for rule, (_, field, cap) in RULES.items()
        if rule in rules and metric.actual(rule) > cap
    }


def stale_entries(measured: Iterable[Metrics], baseline: Baseline) -> list[str]:
    """Baseline entries naming a file that no longer exists, or no longer needs one."""
    metrics = list(measured)
    live = {m.path for m in metrics}
    slack = {m.path for m in metrics if not entry_for(m)}
    return sorted((set(baseline) - live) | (set(baseline) & slack))


def _revision() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return done.stdout.strip()


def grew(recorded: Baseline, entries: Baseline) -> list[str]:
    """Every way the new measurement is larger than the recorded one.

    The per-file check is keyed on the path, so a rename carrying growth with it
    would walk past, and a new entry has nothing to compare against. Each
    field's total covers both. An absent baseline is
    the one case with nothing to compare, so it records whatever it finds.
    """
    if not recorded:
        return []
    growth = [
        f"{path}: {field} {entries.get(path, {}).get(field, 0)}, was {was}"
        for path, entry in sorted(recorded.items())
        for field, was in entry.items()
        if entries.get(path, {}).get(field, 0) > was
    ]
    for _, field, _cap in RULES.values():
        before = sum(entry.get(field, 0) for entry in recorded.values())
        after = sum(entry.get(field, 0) for entry in entries.values())
        if after > before:
            growth.append(f"total baselined {field} {after}, was {before}")
    return growth


def _update() -> int:
    """Re-record the baseline. Never raises a number or the total; a file that grew fails."""
    recorded = load_baseline()
    measured = scan_repo(recorded)
    modules = {
        m.path: entry
        for m in sorted(measured, key=lambda m: m.path)
        if (entry := entry_for(m))
    }

    growth = grew(recorded, modules)
    if growth:
        print("these grew, and the baseline only goes down:", file=sys.stderr)
        for line in growth:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nsplit the file. Where the growth is a split's own bookkeeping, edit "
            "the entry to the measured number by hand and say why in the commit; "
            "the tests pin every entry to today's measurement.",
            file=sys.stderr,
        )
        return 1

    BASELINE.write_text(
        json.dumps({"measured_on": _revision(), "modules": modules}, indent=2) + "\n",
        encoding="utf-8",
    )
    for path in sorted(set(modules) - set(recorded)):
        print(f"new entry: {path} {modules[path]}, review it")
    total = sum(entry.get("lines", 0) for entry in modules.values())
    dropped = len(set(recorded) - set(modules))
    print(f"baseline: {len(modules)} entries, {total} lines, {dropped} dropped")
    return 0


def _report(measured: list[Metrics]) -> None:
    for metric in measured:
        headroom = " ".join(
            f"{rule}{metric.allowed[rule] - metric.actual(rule):+d}"
            for rule in sorted(rules_for(metric.path))
        )
        print(
            f"{metric.lines:5d} lines {metric.public:3d} public ({headroom})  {metric.path}"
        )
    over = sum(1 for m in measured if entry_for(m))
    print(f"\n{len(measured)} files, {over} needing a baseline entry")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--report", action="store_true", help="list every file and exit 0"
    )
    parser.add_argument("--update", action="store_true", help="re-record the baseline")
    args = parser.parse_args(argv)

    if args.update:
        return _update()

    baseline = load_baseline()
    measured = scan_repo(baseline)
    if args.report:
        _report(measured)
        return 0

    failures = gating(measured)
    stale = stale_entries(measured, baseline)
    if failures or stale:
        print("module size budget exceeded:", file=sys.stderr)
        for metric, rule in failures:
            print(f"  {metric.render(rule)}", file=sys.stderr)
        for path in stale:
            print(f"  {path}: baseline entry no longer needed", file=sys.stderr)
        print(
            "\nsplit the module; `--update` re-records the baseline and only ever "
            "lowers a number",
            file=sys.stderr,
        )
        return 1

    print("module sizes ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
