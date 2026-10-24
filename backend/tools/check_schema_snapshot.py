"""Check that the migrations rebuild production's schema (``sql/schema.sql``).

Takes a schema-only dump of a database built from every migration (the local
Supabase stack) and compares it with the production snapshot, ignoring comments
and blank lines. Migrations not yet applied in production are listed in
``PENDING_IN_PRODUCTION`` with the lines they change; any other difference fails.

    npx --prefix frontend supabase db dump --local --workdir . -f <dump>   # repo root
    uv run python -m tools.check_schema_snapshot <dump>                    # backend/
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"

#: Lines each unapplied migration removes from, and adds to, production's schema.
#: Empty this entry (and refresh the snapshot) once production applies it.
PENDING_IN_PRODUCTION: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "006_enable_rls_public_tables.sql": (
        frozenset(
            {
                'CREATE POLICY "Allow public read access" ON "public"."email_source_mappings" FOR SELECT USING (true);',
                'CREATE POLICY "Service role insert newsletters" ON "public"."newsletters" FOR INSERT WITH CHECK (false);',
                'CREATE POLICY "Service role update newsletters" ON "public"."newsletters" FOR UPDATE USING (false);',
            }
        ),
        frozenset(
            {
                'CREATE POLICY "Block non-service inserts" ON "public"."newsletters" FOR INSERT WITH CHECK (false);',
                'CREATE POLICY "Block non-service updates" ON "public"."newsletters" FOR UPDATE USING (false);',
            }
        ),
    ),
}

# A trailing "-- comment" after SQL on the same line.
_TRAILING_COMMENT = re.compile(r"\s+--\s.*$")


def schema_lines(dump: str) -> Counter[str]:
    """Count a dump's statement lines, without comments or blank lines."""
    lines = (_TRAILING_COMMENT.sub("", line).rstrip() for line in dump.splitlines())
    return Counter(line for line in lines if line and not line.startswith("--"))


def unexpected_differences(snapshot: str, dump: str) -> tuple[list[str], list[str]]:
    """Lines only in the snapshot, and only in the dump, beyond the pending migrations."""
    snapshot_lines, dump_lines = schema_lines(snapshot), schema_lines(dump)
    removed = set().union(*(pending[0] for pending in PENDING_IN_PRODUCTION.values()))
    added = set().union(*(pending[1] for pending in PENDING_IN_PRODUCTION.values()))
    only_in_snapshot = snapshot_lines - dump_lines
    only_in_dump = dump_lines - snapshot_lines
    return (
        sorted(line for line in only_in_snapshot if line not in removed),
        sorted(line for line in only_in_dump if line not in added),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "dump", type=Path, help="schema-only dump of the migrated database"
    )
    args = parser.parse_args(argv)

    only_in_snapshot, only_in_dump = unexpected_differences(
        SNAPSHOT_PATH.read_text(encoding="utf-8"), args.dump.read_text(encoding="utf-8")
    )
    if not only_in_snapshot and not only_in_dump:
        print(
            "Migrations match sql/schema.sql (apart from migrations pending in production)."
        )
        return 0
    print("Migrations and sql/schema.sql differ:")
    for line in only_in_snapshot:
        print(f"  only in sql/schema.sql:  {line}")
    for line in only_in_dump:
        print(f"  only in the migrations:  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
