"""Bound the size and prose content of docstrings and comment blocks.

Ruff governs docstring format; nothing upstream bounds length or inspects
prose. ``RULES`` lists what is checked. A rule in ``FROZEN`` is ratcheted by
site count instead of gated per site; the count may only go down.

    uv run python -m tools.lint.check_docstrings            # gate
    uv run python -m tools.lint.check_docstrings --report   # list every site

Suppress one site with ``# noqa: DS002`` on the ``def``/``class`` line, on a
comment line above a module docstring, or on the first line of a comment block
(or the flagged comment line itself), with a reason. ``pyproject.toml``
declares ``DS`` in ``lint.external`` so ruff accepts the code.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tools.lint.source_trees import physical_lines, python_files

#: ``backend/``: this file sits two directories below it.
ROOT = Path(__file__).resolve().parents[2]

MODULE_DOC_MAX = 15
#: A CLI entry module's docstring is its usage documentation.
MODULE_DOC_MAX_CLI = 30
DEF_DOC_MAX = 10
COMMENT_BLOCK_MAX = 6

RULES = {
    "DS001": (
        f"module docstring over {MODULE_DOC_MAX} lines "
        f"({MODULE_DOC_MAX_CLI} for a CLI entry module)"
    ),
    "DS002": f"def/class docstring over {DEF_DOC_MAX} lines",
    "DS003": f"comment block over {COMMENT_BLOCK_MAX} lines",
    "DS101": "planning-doc citation",
    "DS102": "ISO date",
    "DS106": "superseded-alternative narrative",
}

#: Reported, never gated. CLI usage examples carry real dates (``--since``),
#: and DS106 is a keyword heuristic that fires on ordinary prose.
ADVISORY = frozenset({"DS102", "DS106"})

#: Rules gated by a site count instead of per site: lower a count freely, never
#: raise it; a test fails when it is above the measured count. Empty: every rule
#: gates per site.
FROZEN: dict[str, int] = {}

_PLANNING_DOC = re.compile(r"feature_planning/|handoff_archive/|HANDOFF|docs/plans")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SUPERSEDED = re.compile(
    r"\b(?:superseded|refuted|historically|used to|[Cc]hosen over|no longer)\b"
)

_PROSE_RULES = (
    ("DS101", _PLANNING_DOC),
    ("DS102", _ISO_DATE),
    ("DS106", _SUPERSEDED),
)

_NOQA = re.compile(
    r"#\s*noqa:\s*(?P<codes>[A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)", re.IGNORECASE
)


@dataclass(frozen=True)
class Violation:
    """One rule tripped at one place. ``detail`` is the offending text or size."""

    path: str
    line: int
    rule: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {RULES[self.rule]}: {self.detail}"


def _is_cli_entry(tree: ast.Module) -> bool:
    """Whether the module has a top-level ``if __name__ == "__main__":``."""
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        if (
            isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        ):
            return True
    return False


def _noqa_codes(lines: list[str], start: int, end: int) -> set[str]:
    """Codes suppressed by any ``# noqa:`` in the inclusive 1-based line range."""
    codes: set[str] = set()
    for lineno in range(max(start, 1), min(end, len(lines)) + 1):
        match = _NOQA.search(lines[lineno - 1])
        if match is not None:
            codes |= {code.strip().upper() for code in match["codes"].split(",")}
    return codes


def _prose_violations(path: str, text: str, lineno: int) -> Iterator[Violation]:
    for offset, line in enumerate(physical_lines(text)):
        for rule, pattern in _PROSE_RULES:
            found = pattern.search(line)
            if found is not None:
                yield Violation(path, lineno + offset, rule, found.group(0).strip())


def _docstring_nodes(tree: ast.Module) -> Iterator[tuple[str, ast.Constant, int, int]]:
    """Yield ``(rule, docstring node, noqa first line, noqa last line)`` per docstring.

    The noqa range runs from the owning ``def``/``class`` line (or the top of
    the file, for a module) up to the line before the docstring opens.
    """
    owners = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, owners):
            continue
        body = node.body
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        rule = "DS001" if isinstance(node, ast.Module) else "DS002"
        start = 1 if isinstance(node, ast.Module) else node.lineno
        yield rule, value, start, max(value.lineno - 1, start)


def _comment_blocks(source: str) -> Iterator[tuple[int, list[str]]]:
    """Yield ``(first line, comment texts)`` for each run of whole-line comments."""
    lines = physical_lines(source)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return
    block: list[str] = []
    start = 0
    previous = 0
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        lineno = token.start[0]
        if not lines[lineno - 1].lstrip().startswith("#"):
            continue
        if block and lineno == previous + 1:
            block.append(token.string)
        else:
            if block:
                yield start, block
            block = [token.string]
            start = lineno
        previous = lineno
    if block:
        yield start, block


def check_source(source: str, rel: str) -> list[Violation]:
    """Return every violation in one file's source, ``rel`` being its path from ``backend/``."""
    lines = physical_lines(source)
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [Violation(rel, error.lineno or 1, "DS001", f"unparseable: {error.msg}")]

    module_cap = MODULE_DOC_MAX_CLI if _is_cli_entry(tree) else MODULE_DOC_MAX
    found: list[Violation] = []
    for rule, node, noqa_start, noqa_end in _docstring_nodes(tree):
        span = (node.end_lineno or node.lineno) - node.lineno + 1
        cap = module_cap if rule == "DS001" else DEF_DOC_MAX
        suppressed = _noqa_codes(lines, noqa_start, noqa_end)
        if span > cap and rule not in suppressed:
            found.append(Violation(rel, node.lineno, rule, f"{span} lines"))
        text = node.value if isinstance(node.value, str) else ""
        found.extend(
            v
            for v in _prose_violations(rel, text, node.lineno)
            if v.rule not in suppressed
        )

    for start, block in _comment_blocks(source):
        suppressed = _noqa_codes(lines, start, start)
        if len(block) > COMMENT_BLOCK_MAX and "DS003" not in suppressed:
            found.append(Violation(rel, start, "DS003", f"{len(block)} lines"))
        for offset, comment in enumerate(block):
            lineno = start + offset
            line_suppressed = suppressed | _noqa_codes(lines, lineno, lineno)
            found.extend(
                v
                for v in _prose_violations(rel, comment, lineno)
                if v.rule not in line_suppressed
            )
    return found


def scan_repo(root: Path = ROOT) -> list[Violation]:
    """Every violation in the scanned trees, sorted by path and line."""
    found: list[Violation] = []
    for path in python_files(root):
        rel = path.relative_to(root).as_posix()
        found.extend(check_source(path.read_text(encoding="utf-8-sig"), rel))
    return sorted(found, key=lambda v: (v.path, v.line, v.rule))


def gating(violations: Iterable[Violation]) -> list[Violation]:
    """Violations that fail the build on their own: advisory and ratcheted rules dropped."""
    return [v for v in violations if v.rule not in ADVISORY and v.rule not in FROZEN]


def ratchet_counts(violations: Iterable[Violation]) -> dict[str, int]:
    """How many sites each ratcheted rule has."""
    counts = dict.fromkeys(FROZEN, 0)
    for violation in violations:
        if violation.rule in counts:
            counts[violation.rule] += 1
    return counts


def ratchet_failures(violations: Iterable[Violation]) -> list[str]:
    """One message per ratcheted rule whose count is over its frozen number."""
    return [
        f"{rule} {RULES[rule]}: {count} sites, frozen at {FROZEN[rule]}"
        for rule, count in ratchet_counts(violations).items()
        if count > FROZEN[rule]
    ]


def _report(violations: list[Violation]) -> None:
    for violation in violations:
        if violation.rule not in ADVISORY:
            print(violation.render())
    advisory = [v for v in violations if v.rule in ADVISORY]
    if advisory:
        print(f"\nadvisory ({len(advisory)}), never a failure:")
        for violation in advisory:
            print(f"  {violation.render()}")
    for rule, count in ratchet_counts(violations).items():
        print(f"\n{rule}: {count} sites, frozen at {FROZEN[rule]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--report", action="store_true", help="list every site and exit 0"
    )
    args = parser.parse_args(argv)

    violations = scan_repo(ROOT)
    if args.report:
        _report(violations)
        print(f"\n{len(violations)} sites in {len({v.path for v in violations})} files")
        return 0

    failures = gating(violations)
    over = ratchet_failures(violations)
    if failures or over:
        print("docstring budget exceeded:", file=sys.stderr)
        for violation in failures:
            print(f"  {violation.render()}", file=sys.stderr)
        for message in over:
            print(f"  {message} (--report lists them)", file=sys.stderr)
        print(
            "\nshorten the docstring or comment; `# noqa: DSNNN` with a reason is "
            "the deliberate, reviewable exception",
            file=sys.stderr,
        )
        return 1

    print("docstrings ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
