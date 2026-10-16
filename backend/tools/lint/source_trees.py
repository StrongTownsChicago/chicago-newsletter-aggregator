"""The backend trees the lint tools scan, shared so every tool agrees on scope."""

from pathlib import Path

#: The top-level product packages, each run from ``backend/``.
PRODUCT_PACKAGES = (
    "analytics",
    "config",
    "ingest",
    "models",
    "notifications",
    "processing",
    "prompts",
    "shared",
    "utils",
)

TREES = (*PRODUCT_PACKAGES, "tests", "tools")

SKIPPED_DIRECTORIES = frozenset(
    {".venv", "data", "samples", "migrations", "htmlcov", "__pycache__"}
)


def python_files(root: Path, trees: tuple[str, ...] = TREES) -> list[Path]:
    """Every ``.py`` file under ``root``'s scanned trees, in a stable order."""
    files: list[Path] = []
    for tree in trees:
        directory = root / tree
        if not directory.is_dir():
            continue
        files.extend(
            path
            for path in sorted(directory.rglob("*.py"))
            if not SKIPPED_DIRECTORIES.intersection(path.relative_to(root).parts)
        )
    return files
