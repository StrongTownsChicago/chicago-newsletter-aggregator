"""Base test case for tests that run against the local Supabase stack.

Settings come only from ``TEST_SUPABASE_*`` variables, never ``backend/.env``
(which points at production); without them the tests skip. Each test class
starts from empty app tables, and every client created while it runs, by the
test or by app code through ``shared.db``, is checked to be local first.
"""

import os
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, cast
from unittest.mock import patch

import psycopg
import supabase as supabase_package
from postgrest.exceptions import APIError
from supabase import Client

from tests.db_integration.local_guard import abort_unless_local

TEST_ENV = {
    "url": "TEST_SUPABASE_URL",
    "service_key": "TEST_SUPABASE_SERVICE_KEY",
    "anon_key": "TEST_SUPABASE_ANON_KEY",
    "db_url": "TEST_SUPABASE_DB_URL",
}

#: Child tables first is not needed (CASCADE), but every app table is listed so
#: none keeps rows from an earlier class.
APP_TABLES = (
    "notification_history",
    "notification_queue",
    "notification_rules",
    "weekly_topic_reports",
    "user_profiles",
    "email_source_mappings",
    "newsletters",
    "sources",
)

TEST_PASSWORD = "local-test-password"


@dataclass(frozen=True)
class LocalStack:
    """URLs and demo keys of the local stack under test."""

    url: str
    service_key: str
    anon_key: str
    db_url: str


def read_local_stack() -> LocalStack | None:
    """The stack named by ``TEST_SUPABASE_*``, or None when any is unset."""
    values = {field: os.environ.get(name, "") for field, name in TEST_ENV.items()}
    if not all(values.values()):
        return None
    return LocalStack(**values)


def ensure_stack_is_local(stack: LocalStack) -> None:
    """End the process unless every URL and key of ``stack`` is local."""
    abort_unless_local(stack.url, stack.service_key)
    abort_unless_local(stack.url, stack.anon_key)
    abort_unless_local(stack.db_url)


def create_local_client(url: str, key: str, *args: Any, **kwargs: Any) -> Client:
    """``supabase.create_client``, refusing anything but the local stack."""
    abort_unless_local(url, key)
    client = supabase_package.create_client(url, key, *args, **kwargs)
    abort_unless_local(str(client.supabase_url), key)
    return client


def response_rows(response: Any) -> list[dict[str, Any]]:
    """A PostgREST response's rows, typed as the tests read them."""
    return cast(list[dict[str, Any]], response.data)


def reset_database(db_url: str) -> None:
    """Empty every app table and delete every auth user (and so every profile)."""
    abort_unless_local(db_url)
    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute(f"TRUNCATE {', '.join(APP_TABLES)} RESTART IDENTITY CASCADE")
        connection.execute("DELETE FROM auth.users")


class LocalSupabaseTestCase(unittest.TestCase):
    """Runs against the local stack; app tables are emptied once per class.

    Subclasses add their rows in ``setUpClass`` after calling super, or in
    ``setUp`` (calling ``reset`` first) when tests change what they share.
    """

    stack: ClassVar[LocalStack]
    db: ClassVar[Client]

    @classmethod
    def setUpClass(cls) -> None:
        stack = read_local_stack()
        if stack is None:
            raise unittest.SkipTest(
                "local Supabase not configured: set "
                + ", ".join(TEST_ENV.values())
                + " (see CLAUDE.md, Local Supabase)"
            )
        ensure_stack_is_local(stack)
        cls.stack = stack
        # App code builds its client from these, through shared.db.
        cls._start_class_patch(
            patch.dict(
                os.environ,
                {"SUPABASE_URL": stack.url, "SUPABASE_SERVICE_KEY": stack.service_key},
            )
        )
        cls._start_class_patch(patch("shared.db.create_client", create_local_client))
        cls.reset()
        cls.db = create_local_client(stack.url, stack.service_key)

    @classmethod
    def _start_class_patch(cls, patcher: Any) -> None:
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    @classmethod
    def reset(cls) -> None:
        reset_database(cls.stack.db_url)

    @classmethod
    def run_sql(cls, query: str, params: Any = None) -> list[tuple[Any, ...]]:
        """Run one statement as the database owner (bypasses RLS); returns rows."""
        abort_unless_local(cls.stack.db_url)
        with psycopg.connect(cls.stack.db_url, autocommit=True) as connection:
            cursor = connection.execute(query, params)
            return cursor.fetchall() if cursor.description else []

    @classmethod
    def anon_client(cls) -> Client:
        return create_local_client(cls.stack.url, cls.stack.anon_key)

    @classmethod
    def user_client(cls, email: str) -> Client:
        """A client signed in as ``email`` (created with ``TEST_PASSWORD``)."""
        client = cls.anon_client()
        client.auth.sign_in_with_password({"email": email, "password": TEST_PASSWORD})
        return client

    def rows(
        self, table: str, columns: str = "*", **equal: Any
    ) -> list[dict[str, Any]]:
        """Every row of ``table`` matching ``equal``, read with the service key."""
        query = self.db.table(table).select(columns)
        for column, value in equal.items():
            query = query.eq(column, value)
        return response_rows(query.execute())

    def assert_api_error(self, code: str, action: Callable[[], Any]) -> None:
        """``action`` fails with the Postgres or PostgREST error ``code``."""
        with self.assertRaises(APIError) as caught:
            action()
        self.assertEqual(caught.exception.code, code, caught.exception.message)
