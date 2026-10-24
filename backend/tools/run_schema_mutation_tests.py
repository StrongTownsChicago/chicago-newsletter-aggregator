"""
Mutation testing for the database schema, against the database tests.

Each mutant weakens one object on the local Supabase stack (tools/schema_mutants.py):
row-level security, a policy, a constraint, a default, a trigger or an operator in a
SQL function. The tests in tests/db_integration run against it, then the object is
restored; a mutant they still pass on ("survivor") is schema behaviour no test pins
down. Dev-only, not a CI step; a full run takes about an hour.

Needs the local stack and TEST_SUPABASE_* (CLAUDE.md, Local Supabase). Nothing else
may use the stack while it runs. If the run is killed mid-mutant, rebuild the schema
with `npx --prefix frontend supabase db reset --local --workdir .`.

Usage:
    uv run python -m tools.run_schema_mutation_tests [--list] [--match TEXT ...]
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

import psycopg

from tests.db_integration.local_supabase import (
    ensure_stack_is_local,
    read_local_stack,
    reset_database,
)
from tools.run_mutation_tests import BACKEND_ROOT
from tools.schema_mutants import (
    ColumnDefault,
    Constraint,
    Function,
    Policy,
    SchemaCatalog,
    SchemaMutant,
    TableName,
    Trigger,
    UniqueIndex,
    generate_mutants,
)

RESET_COMMAND = "npx --prefix frontend supabase db reset --local --workdir ."
#: Per test run; a mutant that makes the tests hang counts as killed.
TEST_TIMEOUT_SECONDS = 600
DATABASE_TESTS = BACKEND_ROOT / "tests" / "db_integration"
#: The tests that pin the schema directly run first, so most mutants die early.
SCHEMA_TEST_MODULES = (
    "test_row_level_security",
    "test_schema_constraints",
    "test_sql_functions",
)


def database_test_modules() -> list[str]:
    """Every database test module, as dotted names, the schema tests first."""
    others = sorted(
        path.stem
        for path in DATABASE_TESTS.glob("test_*.py")
        if path.stem not in SCHEMA_TEST_MODULES
    )
    return [f"tests.db_integration.{name}" for name in (*SCHEMA_TEST_MODULES, *others)]


_PUBLIC_TABLE = "c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'"
CATALOG_QUERIES = {
    "rls_tables": f"""
        SELECT 'public', c.relname FROM pg_class c
        WHERE {_PUBLIC_TABLE} AND c.relrowsecurity ORDER BY 2""",
    # Comments are read too: dropping an object drops its comment, so a restore
    # must put it back, and the check after each restore must see it.
    "policies": """
        SELECT 'public', c.relname, p.polname, pp.cmd, pp.roles::text[],
               p.polpermissive, pp.qual, pp.with_check,
               obj_description(p.oid, 'pg_policy')
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_policies pp ON pp.schemaname = 'public'
          AND pp.tablename = c.relname AND pp.policyname = p.polname
        WHERE c.relnamespace = 'public'::regnamespace
        ORDER BY 2, 3""",
    "constraints": """
        SELECT 'public', c.relname, k.conname, k.contype,
               pg_get_constraintdef(k.oid), obj_description(k.oid, 'pg_constraint')
        FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
        WHERE k.connamespace = 'public'::regnamespace AND k.contype IN ('c', 'u', 'f')
        ORDER BY 2, 3""",
    "unique_indexes": f"""
        SELECT 'public', c.relname, ic.relname, pg_get_indexdef(i.indexrelid),
               obj_description(i.indexrelid, 'pg_class')
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_class ic ON ic.oid = i.indexrelid
        WHERE {_PUBLIC_TABLE} AND i.indisunique AND NOT i.indisprimary
          AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid)
        ORDER BY 2, 3""",
    "column_defaults": f"""
        SELECT 'public', c.relname, a.attname, pg_get_expr(d.adbin, d.adrelid)
        FROM pg_attrdef d
        JOIN pg_class c ON c.oid = d.adrelid
        JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
        WHERE {_PUBLIC_TABLE} AND a.attgenerated = ''
        ORDER BY 2, 3""",
    # Triggers on any table (the profile trigger is on auth.users) that run a public function.
    "triggers": """
        SELECT n.nspname, c.relname, t.tgname, pg_get_triggerdef(t.oid),
               obj_description(t.oid, 'pg_trigger')
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE NOT t.tgisinternal AND p.pronamespace = 'public'::regnamespace
        ORDER BY 1, 2, 3""",
    "functions": """
        SELECT p.oid::regprocedure::text, pg_get_functiondef(p.oid)
        FROM pg_proc p
        WHERE p.pronamespace = 'public'::regnamespace AND p.prokind = 'f'
          AND NOT EXISTS (
            SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
        ORDER BY 1""",
}


def read_catalog(connection: psycopg.Connection[Any]) -> SchemaCatalog:
    def rows(name: str) -> list[tuple[Any, ...]]:
        return connection.execute(CATALOG_QUERIES[name]).fetchall()

    return SchemaCatalog(
        rls_tables=tuple(TableName(*row) for row in rows("rls_tables")),
        policies=tuple(
            Policy(TableName(schema, table), name, command, tuple(roles), *rest)
            for schema, table, name, command, roles, *rest in rows("policies")
        ),
        constraints=tuple(
            Constraint(TableName(schema, table), *rest)
            for schema, table, *rest in rows("constraints")
        ),
        unique_indexes=tuple(
            UniqueIndex(TableName(schema, table), *rest)
            for schema, table, *rest in rows("unique_indexes")
        ),
        column_defaults=tuple(
            ColumnDefault(TableName(schema, table), *rest)
            for schema, table, *rest in rows("column_defaults")
        ),
        triggers=tuple(
            Trigger(TableName(schema, table), *rest)
            for schema, table, *rest in rows("triggers")
        ),
        functions=tuple(Function(*row) for row in rows("functions")),
    )


def execute_all(db_url: str, statements: Sequence[str]) -> None:
    """Run ``statements`` in one transaction."""
    with psycopg.connect(db_url) as connection:
        for statement in statements:
            connection.execute(statement.encode())


def database_tests_pass() -> bool:
    try:
        completed = subprocess.run(
            # -f: one failure is enough to kill a mutant.
            [sys.executable, "-m", "unittest", "-f", "-q", *database_test_modules()],
            cwd=BACKEND_ROOT,
            capture_output=True,
            timeout=TEST_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def run_mutant(db_url: str, mutant: SchemaMutant, original: SchemaCatalog) -> str:
    """Apply ``mutant``, run the tests and restore it; "killed", "survived" or "invalid"."""
    try:
        execute_all(db_url, mutant.apply)
    except psycopg.OperationalError:
        raise  # the database, not the mutant
    except psycopg.Error:
        return "invalid"
    try:
        outcome = "killed" if not database_tests_pass() else "survived"
    finally:
        # Rows the tests left could break a restored constraint.
        reset_database(db_url)
        execute_all(db_url, mutant.restore)
    with psycopg.connect(db_url) as connection:
        if read_catalog(connection) != original:
            sys.exit(
                f"restoring {mutant.label!r} left the schema changed; "
                f"reset it: {RESET_COMMAND}"
            )
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="list mutants, run none")
    parser.add_argument(
        "--match",
        action="append",
        default=[],
        help="only mutants whose label contains this text (repeatable)",
    )
    arguments = parser.parse_args()

    stack = read_local_stack()
    if stack is None:
        sys.exit("set TEST_SUPABASE_* (scripts/supabase-test-env.sh prints them)")
    ensure_stack_is_local(stack)
    with psycopg.connect(stack.db_url) as connection:
        original = read_catalog(connection)
    mutants = [
        mutant
        for mutant in generate_mutants(original)
        if not arguments.match or any(text in mutant.label for text in arguments.match)
    ]
    if arguments.list:
        print("\n".join(f"[{m.kind}] {m.label}" for m in mutants))
        return

    # Without a passing baseline every mutant counts as killed.
    if not database_tests_pass():
        sys.exit("the database tests fail without any mutation")
    outcomes: dict[str, list[SchemaMutant]] = {}
    for number, mutant in enumerate(mutants, start=1):
        try:
            outcome = run_mutant(stack.db_url, mutant, original)
        except psycopg.Error as error:
            sys.exit(
                f"database error during {mutant.label!r} ({error}); "
                f"the schema may still hold the mutant: {RESET_COMMAND}"
            )
        outcomes.setdefault(outcome, []).append(mutant)
        print(f"[{number}/{len(mutants)}] {outcome}: {mutant.label}", flush=True)

    print(", ".join(f"{len(group)} {name}" for name, group in sorted(outcomes.items())))
    # An invalid mutant failed to apply, so it tested nothing.
    for mutant in outcomes.get("invalid", []):
        print(f"\nINVALID [{mutant.kind}] {mutant.label}")
    for mutant in outcomes.get("survived", []):
        print(f"\nSURVIVED [{mutant.kind}] {mutant.label}")
        print("\n".join(f"    {statement}" for statement in mutant.apply))


if __name__ == "__main__":
    main()
