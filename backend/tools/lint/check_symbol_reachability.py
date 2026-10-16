"""Find product symbols no live consumer imports.

``.importlinter`` asks whether a package may import another. This asks, of each
module-level ``def``/``class``, whether anything outside its own module and the
tests imports it: a function whose only importer is its own test is dead.

Import edges are resolved, never name-matched: a same-named local ``def`` or a
keyword argument would otherwise read as a use. Nothing is imported or
executed; this is an AST pass.

    uv run python -m tools.lint.check_symbol_reachability            # gate
    uv run python -m tools.lint.check_symbol_reachability --report   # every finding
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tools.lint.source_trees import PRODUCT_PACKAGES, python_files

#: ``backend/``: this file sits two directories below it.
ROOT = Path(__file__).resolve().parents[2]

#: The ratchet, not a target: lower it freely, never raise it. A test fails
#: when it is above the measured count. Held up by test-only or unused symbols
#: in lenses, email_parser, email_sender, unsubscribe_tokens and
#: cost_report_generator; ``--report`` names them.
FROZEN_FINDINGS = 5

#: Consumers whose import does NOT keep a symbol alive, as (tier, tree).
#: Letting a test hold a symbol alive would pin dead code forever.
DEAD_TIERS = (("tests", "tests"),)

#: Trees whose imports keep a symbol alive. ``tools/`` is neither scanned nor live.
LIVE_TREES = PRODUCT_PACKAGES


@dataclass(frozen=True)
class Finding:
    """One module-level symbol with no live importer."""

    module: str
    symbol: str
    line: int
    reason: str

    def render(self) -> str:
        return f"{self.module}.{self.symbol}:{self.line}: {self.reason}"


def _is_product(name: str) -> bool:
    return name.split(".")[0] in PRODUCT_PACKAGES


def _module_name(path: Path, root: Path) -> str:
    """Dotted name of a file relative to ``root``; a package ``__init__`` is the package."""
    parts = list(path.relative_to(root).parts)
    parts[-1] = parts[-1].removesuffix(".py")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _anchor(module: str, is_package: bool, level: int) -> str:
    """Base a relative import resolves against: a package at itself, a module at its parent."""
    parts = module.split(".")
    if not is_package:
        parts.pop()
    return ".".join(parts[: len(parts) - (level - 1)]) if level > 1 else ".".join(parts)


def _resolved(node: ast.ImportFrom, module: str | None, is_package: bool) -> str | None:
    """Absolute module an ``ImportFrom`` names, or None when it cannot be anchored."""
    if not node.level:
        return node.module
    if module is None:
        return None
    base = _anchor(module, is_package, node.level)
    return f"{base}.{node.module}" if node.module else base


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _definitions(body: Iterable[ast.stmt]) -> Iterator[tuple[str, int]]:
    """Module-level ``def``/``class``, including those under a module-level ``if``/``try``.

    Dunders such as ``__getattr__`` are called by the interpreter, never imported.
    """
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in body:
        if isinstance(node, definitions) and not _is_dunder(node.name):
            yield node.name, node.lineno
        elif isinstance(node, ast.If | ast.Try):
            yield from _definitions(node.body)
            yield from _definitions(node.orelse)
            if isinstance(node, ast.Try):
                yield from _definitions(node.finalbody)
                for handler in node.handlers:
                    yield from _definitions(handler.body)


def _dunder_all(tree: ast.Module) -> set[str]:
    """Names listed in a module-level ``__all__`` literal."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        if isinstance(node.value, ast.List | ast.Tuple | ast.Set):
            return {
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    return set()


def _local_references(tree: ast.Module, defined: set[str]) -> set[str]:
    """Defined names this module mentions anywhere other than their own header.

    A call, a decorator, a default argument or ``if __name__ == "__main__": main()``
    all count. An attribute access does not: ``other.helper()`` names a method.
    """
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in defined
    }


def _dotted(node: ast.Attribute) -> list[str] | None:
    """Flatten ``a.b.c`` to ``["a", "b", "c"]``; None when the head is not a name."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return list(reversed(parts))


def _module_aliases(
    tree: ast.Module, module: str | None, is_package: bool, modules: set[str]
) -> tuple[dict[str, str], set[tuple[str, str]]]:
    """Names bound to product modules, and ``(module, symbol)`` pairs imported by name."""
    aliases: dict[str, str] = {}
    used: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # `import a.b.c` binds `a`; `import a.b.c as m` binds `m` to `a.b.c`
            aliases.update(
                (alias.asname, alias.name)
                if alias.asname
                else (alias.name.split(".")[0], alias.name.split(".")[0])
                for alias in node.names
                if _is_product(alias.name)
            )
        elif isinstance(node, ast.ImportFrom):
            target = _resolved(node, module, is_package)
            if target is None or not _is_product(target):
                continue
            for alias in node.names:
                if alias.name == "*":
                    # ruff's F403 forbids star imports, so one here is refused
                    # rather than silently dropped
                    raise ValueError(
                        f"star import of {target}: this check cannot resolve one"
                    )
                child = f"{target}.{alias.name}"
                if child in modules:
                    aliases[alias.asname or alias.name] = child
                else:
                    used.add((target, alias.name))
    return aliases, used


def _imported_symbols(
    tree: ast.Module, module: str | None, is_package: bool, modules: set[str]
) -> set[tuple[str, str]]:
    """``(module, symbol)`` pairs this file binds from the product packages.

    Covers ``from pkg.mod import name``, ``import pkg.mod as alias`` followed by
    ``alias.name``, and ``from pkg import mod`` followed by ``mod.name``.
    """
    aliases, used = _module_aliases(tree, module, is_package, modules)
    if not aliases:
        return used
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        parts = _dotted(node)
        if parts is None or parts[0] not in aliases:
            continue
        parts = aliases[parts[0]].split(".") + parts[1:]
        for cut in range(len(parts) - 1, 0, -1):
            candidate = ".".join(parts[:cut])
            if candidate in modules:
                used.add((candidate, parts[cut]))
                break
    return used


def _tier(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    for name, prefix in DEAD_TIERS:
        if relative.startswith(f"{prefix}/"):
            return name
    return "live"


def _unused_locally(
    trees: dict[str, ast.Module], packages: set[str]
) -> dict[tuple[str, str], int]:
    """``(module, symbol) -> line`` for every symbol its own module never references."""
    unused: dict[tuple[str, str], int] = {}
    for module, tree in trees.items():
        defined = dict(_definitions(tree.body))
        alive = _local_references(tree, set(defined))
        if module in packages:
            # only in a package __init__ does __all__ hold a re-export up; elsewhere,
            # with no star import in the tree, it certifies itself and nothing else
            alive |= _dunder_all(tree)
        unused.update(
            ((module, symbol), line)
            for symbol, line in defined.items()
            if symbol not in alive
        )
    return unused


def scan(root: Path) -> list[Finding]:
    """Every module-level product symbol with no live importer."""
    sources = {
        _module_name(path, root): path for path in python_files(root, LIVE_TREES)
    }
    packages = {
        module for module, path in sources.items() if path.name == "__init__.py"
    }
    modules = set(sources)
    trees = {
        module: ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for module, path in sources.items()
    }
    unused = _unused_locally(trees, packages)
    if not unused:
        return []

    reached: dict[tuple[str, str], set[str]] = {}
    dead_trees = tuple(tree for _, tree in DEAD_TIERS)
    for path in python_files(root, (*LIVE_TREES, *dead_trees)):
        tier = _tier(path, root)
        owner = _module_name(path, root) if tier == "live" else None
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for pair in _imported_symbols(tree, owner, path.name == "__init__.py", modules):
            if pair in unused:
                reached.setdefault(pair, set()).add(tier)

    findings: list[Finding] = []
    for (module, symbol), line in sorted(unused.items()):
        tiers = reached.get((module, symbol), set())
        if "live" in tiers:
            continue
        names = [name for name, _ in DEAD_TIERS if name in tiers]
        reason = (
            f"reached only by {' and '.join(sorted(names))}"
            if names
            else "no importer outside its own module"
        )
        findings.append(Finding(module, symbol, line, reason))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--report", action="store_true", help="list every finding and exit 0"
    )
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="the backend/ directory"
    )
    args = parser.parse_args(argv)

    findings = scan(args.root)
    if args.report:
        for finding in findings:
            print(f"  {finding.render()}")
        print(f"\n{len(findings)} findings, ceiling {FROZEN_FINDINGS}")
        return 0

    if len(findings) > FROZEN_FINDINGS:
        print(
            f"unreachable product symbols: {len(findings)}, over the frozen "
            f"{FROZEN_FINDINGS}:",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding.render()}", file=sys.stderr)
        print(
            "\nwire it into the product, delete it with its test, or lower the "
            "ceiling if you removed one",
            file=sys.stderr,
        )
        return 1

    print(f"symbol reachability ok ({len(findings)}/{FROZEN_FINDINGS})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
