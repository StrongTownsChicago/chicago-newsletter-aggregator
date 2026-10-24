"""Schema mutants: one weakened schema object each, with the SQL that restores it.

Pure: works on catalog rows read elsewhere (tools/run_schema_mutation_tests.py),
so what gets mutated and how is testable without a database.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

#: Supabase's service role has BYPASSRLS: changing a policy only it uses changes nothing.
RLS_BYPASS_ROLES = frozenset({"service_role"})

#: ON DELETE action -> the one it is mutated to.
FOREIGN_KEY_ACTION_SWAPS = {
    "CASCADE": "NO ACTION",
    "SET NULL": "CASCADE",
    "NO ACTION": "CASCADE",
    "RESTRICT": "CASCADE",
    "SET DEFAULT": "CASCADE",
}

#: Defaults that only generate keys; dropping one fails every insert, which says nothing.
KEY_DEFAULT = re.compile(r"^(nextval\(|gen_random_uuid\(\))")


@dataclass(frozen=True)
class TableName:
    schema: str
    name: str

    def sql(self) -> str:
        return f"{quote_identifier(self.schema)}.{quote_identifier(self.name)}"

    def __str__(self) -> str:
        return self.name if self.schema == "public" else f"{self.schema}.{self.name}"


@dataclass(frozen=True)
class Policy:
    table: TableName
    name: str
    command: str
    roles: tuple[str, ...]
    permissive: bool
    using: str | None
    check: str | None


@dataclass(frozen=True)
class Constraint:
    table: TableName
    name: str
    kind: str  # pg_constraint.contype: c(heck), u(nique), f(oreign key)
    definition: str


@dataclass(frozen=True)
class UniqueIndex:
    table: TableName
    name: str
    definition: str


@dataclass(frozen=True)
class ColumnDefault:
    table: TableName
    column: str
    default: str


@dataclass(frozen=True)
class Trigger:
    table: TableName
    name: str
    definition: str


@dataclass(frozen=True)
class Function:
    signature: str  # name(identity arguments), as regprocedure prints it
    definition: str  # pg_get_functiondef: a CREATE OR REPLACE statement


@dataclass(frozen=True)
class SchemaCatalog:
    """The schema objects mutated; read from pg_catalog by the runner."""

    rls_tables: tuple[TableName, ...] = ()
    policies: tuple[Policy, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    unique_indexes: tuple[UniqueIndex, ...] = ()
    column_defaults: tuple[ColumnDefault, ...] = ()
    triggers: tuple[Trigger, ...] = ()
    functions: tuple[Function, ...] = ()


@dataclass(frozen=True)
class SchemaMutant:
    kind: str
    label: str
    apply: tuple[str, ...]
    restore: tuple[str, ...]


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def if_exists(drop: str) -> str:
    """``drop`` with IF EXISTS: a restore can follow a mutant that dropped the object."""
    return re.sub(
        r"\bDROP (POLICY|CONSTRAINT|TRIGGER|INDEX) ",
        r"DROP \1 IF EXISTS ",
        drop,
        count=1,
    )


def generate_mutants(catalog: SchemaCatalog) -> list[SchemaMutant]:
    """Every mutant of ``catalog``, in a stable order."""
    generators: tuple[Callable[[SchemaCatalog], Iterator[SchemaMutant]], ...] = (
        _rls_mutants,
        _policy_mutants,
        _constraint_mutants,
        _unique_index_mutants,
        _default_mutants,
        _trigger_mutants,
        _function_mutants,
    )
    return [mutant for generate in generators for mutant in generate(catalog)]


def _rls_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for table in catalog.rls_tables:
        yield SchemaMutant(
            "rls",
            f"{table}: row-level security disabled",
            (f"ALTER TABLE {table.sql()} DISABLE ROW LEVEL SECURITY",),
            (f"ALTER TABLE {table.sql()} ENABLE ROW LEVEL SECURITY",),
        )


def create_policy_sql(policy: Policy) -> str:
    roles = ", ".join(
        "PUBLIC" if role == "public" else quote_identifier(role)
        for role in policy.roles
    )
    clauses = [
        f"CREATE POLICY {quote_identifier(policy.name)} ON {policy.table.sql()}",
        f"AS {'PERMISSIVE' if policy.permissive else 'RESTRICTIVE'}",
        f"FOR {policy.command} TO {roles}",
    ]
    if policy.using is not None:
        clauses.append(f"USING ({policy.using})")
    if policy.check is not None:
        clauses.append(f"WITH CHECK ({policy.check})")
    return " ".join(clauses)


def _policy_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for policy in catalog.policies:
        label = f"{policy.table} policy {policy.name!r}"
        drop = f"DROP POLICY {quote_identifier(policy.name)} ON {policy.table.sql()}"
        restore = (if_exists(drop), create_policy_sql(policy))
        conditions = [c for c in (policy.using, policy.check) if c is not None]
        only_bypass_roles = set(policy.roles) <= RLS_BYPASS_ROLES
        # A permissive policy that grants nothing changes nothing when dropped.
        grants_nothing = policy.permissive and all(c == "false" for c in conditions)
        if not only_bypass_roles and not grants_nothing:
            yield SchemaMutant("policy", f"{label}: dropped", (drop,), restore)
        if not only_bypass_roles and any(c != "true" for c in conditions):
            loosened = replace(
                policy,
                using=None if policy.using is None else "true",
                check=None if policy.check is None else "true",
            )
            yield SchemaMutant(
                "policy",
                f"{label}: condition replaced with true",
                (drop, create_policy_sql(loosened)),
                restore,
            )
        if policy.roles != ("public",):
            widened = replace(policy, roles=("public",))
            yield SchemaMutant(
                "policy",
                f"{label}: applies to every role",
                (drop, create_policy_sql(widened)),
                restore,
            )


def _constraint_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for constraint in catalog.constraints:
        table, name = constraint.table.sql(), quote_identifier(constraint.name)
        drop = f"ALTER TABLE {table} DROP CONSTRAINT {name}"
        add = f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        restore = (if_exists(drop), add + constraint.definition)
        label = f"{constraint.table} constraint {constraint.name}"
        if constraint.kind == "f":
            mutated, change = swap_foreign_key_action(constraint.definition)
            yield SchemaMutant(
                "foreign_key", f"{label}: {change}", (drop, add + mutated), restore
            )
            continue
        kind = "check" if constraint.kind == "c" else "unique"
        yield SchemaMutant(kind, f"{label}: dropped", (drop,), restore)
        if constraint.kind == "c":
            for change, mutated in operator_variants(constraint.definition):
                yield SchemaMutant(
                    "check", f"{label}: {change}", (drop, add + mutated), restore
                )


def swap_foreign_key_action(definition: str) -> tuple[str, str]:
    """``definition`` with its ON DELETE action swapped, and what changed."""
    match = re.search(r"ON DELETE (CASCADE|SET NULL|SET DEFAULT|RESTRICT)", definition)
    action = match.group(1) if match else "NO ACTION"
    replacement = FOREIGN_KEY_ACTION_SWAPS[action]
    if match:
        mutated = definition.replace(match.group(0), f"ON DELETE {replacement}")
    else:
        mutated = f"{definition} ON DELETE {replacement}"
    return mutated, f"ON DELETE {action} -> {replacement}"


def _unique_index_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for index in catalog.unique_indexes:
        name = f"{quote_identifier(index.table.schema)}.{quote_identifier(index.name)}"
        yield SchemaMutant(
            "unique",
            f"{index.table} unique index {index.name}: dropped",
            (f"DROP INDEX {name}",),
            (f"DROP INDEX IF EXISTS {name}", index.definition),
        )


def _default_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for column_default in catalog.column_defaults:
        if KEY_DEFAULT.match(column_default.default):
            continue
        alter = (
            f"ALTER TABLE {column_default.table.sql()} "
            f"ALTER COLUMN {quote_identifier(column_default.column)}"
        )
        yield SchemaMutant(
            "default",
            f"{column_default.table}.{column_default.column}: "
            f"default {column_default.default} dropped",
            (f"{alter} DROP DEFAULT",),
            (f"{alter} SET DEFAULT {column_default.default}",),
        )


def _trigger_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for trigger in catalog.triggers:
        drop = f"DROP TRIGGER {quote_identifier(trigger.name)} ON {trigger.table.sql()}"
        yield SchemaMutant(
            "trigger",
            f"{trigger.table} trigger {trigger.name}: dropped",
            (drop,),
            (if_exists(drop), trigger.definition),
        )


def _function_mutants(catalog: SchemaCatalog) -> Iterator[SchemaMutant]:
    for function in catalog.functions:
        definition = function.definition
        restore = (definition,)
        # pg_get_functiondef puts each clause on its own line; the body is dollar-quoted.
        body_start = re.search(r"\nAS (\$\w*\$)", definition)
        if not body_start:
            continue
        if "\n SECURITY DEFINER" in definition[: body_start.start()]:
            yield SchemaMutant(
                "function",
                f"{function.signature}: SECURITY DEFINER -> INVOKER",
                (definition.replace("\n SECURITY DEFINER", "", 1),),
                restore,
            )
        opening = body_start.end()
        closing = definition.rindex(body_start.group(1))
        for change, mutated in operator_variants(definition[opening:closing]):
            yield SchemaMutant(
                "function",
                f"{function.signature}: {change}",
                (definition[:opening] + mutated + definition[closing:],),
                restore,
            )


#: (pattern, replacement, label) for one-token SQL mutations; case-insensitive.
OPERATOR_MUTATIONS: tuple[tuple[str, Callable[[re.Match[str]], str], str], ...] = (
    (r"<=", lambda _: "<", "<= -> <"),
    (r">=", lambda _: ">", ">= -> >"),
    (r"(?<![<>!:=-])<(?![=>])", lambda _: "<=", "< -> <="),
    (r"(?<![<>!:=-])>(?![=>])", lambda _: ">=", "> -> >="),
    (r"<>|!=", lambda _: "=", "<> -> ="),
    (r"(?<![<>!:=])=(?![>=])", lambda _: "<>", "= -> <>"),
    (r"\bAND\b", lambda _: "OR", "AND -> OR"),
    (r"\bOR\b", lambda _: "AND", "OR -> AND"),
    (r"\bNOT\s+", lambda _: "", "NOT removed"),
    (r"\bDISTINCT\s+", lambda _: "", "DISTINCT removed"),
    (r"\bIS\s+NULL\b", lambda _: "IS NOT NULL", "IS NULL -> IS NOT NULL"),
    (r"\btrue\b", lambda _: "false", "true -> false"),
    (r"\bfalse\b", lambda _: "true", "false -> true"),
    (r"(?<![\w.$])\d+(?![\w.])", lambda m: str(int(m.group(0)) + 1), "n -> n+1"),
)

#: SQL text no mutation may touch: string literals, quoted identifiers, comments.
_PROTECTED = re.compile(
    r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|--[^\n]*|/\*.*?\*/", re.DOTALL
)


def operator_variants(sql: str) -> list[tuple[str, str]]:
    """One (label, mutated SQL) per mutable operator, literal or keyword in ``sql``."""
    protected = [match.span() for match in _PROTECTED.finditer(sql)]

    def is_protected(position: int) -> bool:
        return any(start <= position < end for start, end in protected)

    variants: list[tuple[str, str]] = []
    for pattern, substitute, label in OPERATOR_MUTATIONS:
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            if is_protected(match.start()):
                continue
            line = sql.count("\n", 0, match.start()) + 1
            mutated = sql[: match.start()] + substitute(match) + sql[match.end() :]
            variants.append((f"{label} (line {line})", mutated))
    return variants
