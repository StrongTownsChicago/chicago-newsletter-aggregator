"""A Supabase client stand-in that records every executed query.

Each `table(...)` chain is recorded call by call; `execute()` appends the chain
to `FakeSupabase.executed` and answers from `responses`, keyed by
(table, operation). An answer is the row list to return, an exception to raise,
or a callable that receives the executed query and returns rows.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

OPERATIONS = ("select", "insert", "update", "upsert", "delete")

Response = list[dict[str, Any]] | BaseException | Callable[["ExecutedQuery"], Any]


@dataclass
class ExecutedQuery:
    """One `table(...)...execute()` chain: the table and each call made on it."""

    table: str
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(
        default_factory=list
    )

    @property
    def operation(self) -> str:
        return next((name for name, _, _ in self.calls if name in OPERATIONS), "")

    @property
    def equal_filters(self) -> dict[str, Any]:
        """Column -> value for each `eq` call in the chain."""
        return {args[0]: args[1] for name, args, _ in self.calls if name == "eq"}

    @property
    def payload(self) -> Any:
        """The row an insert, update or upsert wrote."""
        operation = self.operation
        return next(args[0] for name, args, _ in self.calls if name == operation)


class FakeQuery:
    """A chainable query builder: every method records itself and returns self."""

    def __init__(self, client: "FakeSupabase", table: str) -> None:
        self._client = client
        self._query = ExecutedQuery(table)

    def __getattr__(self, name: str) -> Any:
        if name == "not_":
            self._query.calls.append((name, (), {}))
            return self

        def record(*args: Any, **kwargs: Any) -> FakeQuery:
            self._query.calls.append((name, args, kwargs))
            return self

        return record

    def execute(self) -> SimpleNamespace:
        return self._client.answer(self._query)


class FakeSupabase:
    """Records executed queries in order and answers them from `responses`."""

    def __init__(self, responses: dict[tuple[str, str], Response] | None = None):
        self.responses = responses or {}
        self.executed: list[ExecutedQuery] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def answer(self, query: ExecutedQuery) -> SimpleNamespace:
        self.executed.append(query)
        response = self.responses.get((query.table, query.operation), [])
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            response = response(query)
        return SimpleNamespace(data=response)

    def writes(self, table: str | None = None) -> list[ExecutedQuery]:
        """Executed inserts, updates, upserts and deletes, optionally for one table."""
        return [
            query
            for query in self.executed
            if query.operation not in ("select", "")
            and (table is None or query.table == table)
        ]
