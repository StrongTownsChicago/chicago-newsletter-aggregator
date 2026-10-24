"""Row-level security on every public table: anon key, a user's JWT, service key.

``anon`` and ``authenticated`` hold Supabase's default grants on every table,
so these policies are the site's only security boundary.
"""

import json
from functools import partial
from typing import Any, ClassVar

import psycopg
from postgrest.types import ReturnMethod
from supabase import Client

from tests.db_integration.local_guard import abort_unless_local_postgres
from tests.db_integration.local_supabase import (
    TEST_PASSWORD,
    LocalSupabaseTestCase,
    response_rows,
)
from tests.fixtures.newsletter_factory import (
    insert_email_mapping,
    insert_newsletter,
    insert_row,
    insert_source,
)
from tests.fixtures.user_factory import (
    create_auth_user,
    insert_notification,
    insert_rule,
)

RLS_VIOLATION = "42501"

PUBLIC_TABLES = ("sources", "newsletters")
PRIVATE_TABLES = ("email_source_mappings", "weekly_topic_reports")
PER_USER_TABLES = {  # table -> the column naming its owner
    "user_profiles": "id",
    "notification_rules": "user_id",
    "notification_queue": "user_id",
    "notification_history": "user_id",
}
ALL_TABLES = (*PUBLIC_TABLES, *PRIVATE_TABLES, *PER_USER_TABLES)
#: A column each table has, for update attempts; created_at where unlisted.
WRITABLE_COLUMNS = {
    "sources": "name",
    "notification_rules": "name",
    "notification_history": "sent_at",
}


class RowLevelSecurityTestCase(LocalSupabaseTestCase):
    """Two users, each with a rule, a queued notification and a history row."""

    users: ClassVar[dict[str, str]]
    rules: ClassVar[dict[str, dict[str, Any]]]
    source: ClassVar[dict[str, Any]]
    newsletter: ClassVar[dict[str, Any]]
    report: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.source = insert_source(cls.db, name="Ward 5 Office", ward_number=5)
        cls.newsletter = insert_newsletter(cls.db, cls.source["id"])
        insert_email_mapping(cls.db, "%@ward5.example.org", cls.source["id"])
        cls.report = insert_row(
            cls.db,
            "weekly_topic_reports",
            {
                "topic": "city_budget",
                "week_id": "2026-W05",
                "report_summary": "Summary.",
                "newsletter_ids": [cls.newsletter["id"]],
            },
        )
        cls.users, cls.rules = {}, {}
        for name in ("alice", "bob"):
            user_id = create_auth_user(cls.db, f"{name}@example.test", TEST_PASSWORD)
            cls.users[name] = user_id
            cls.rules[name] = insert_rule(cls.db, user_id, name=f"{name}'s rule")
            insert_notification(
                cls.db,
                user_id=user_id,
                rule_id=cls.rules[name]["id"],
                newsletter_id=cls.newsletter["id"],
            )
            insert_row(cls.db, "notification_history", cls.history_row(user_id))

    @staticmethod
    def history_row(user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "newsletter_ids": [],
            "rule_ids": [],
            "delivery_type": "daily_digest",
            "success": True,
        }

    def new_row(self, table: str, owner: str = "alice") -> dict[str, Any]:
        """A valid row for ``table`` that the service key could insert."""
        user_id = self.users[owner]
        rows: dict[str, dict[str, Any]] = {
            "sources": {"source_type": "alderman", "name": "Intruder"},
            "newsletters": {
                "source_id": self.source["id"],
                "subject": "Forged",
                "received_date": "2026-01-01T00:00:00+00:00",
            },
            "email_source_mappings": {
                "email_pattern": "%@forged.example",
                "source_id": self.source["id"],
            },
            "weekly_topic_reports": {
                "topic": "tax_policy",
                "week_id": "2026-W06",
                "report_summary": "Forged.",
                "newsletter_ids": [],
            },
            "user_profiles": {"id": user_id, "email": "forged@example.test"},
            "notification_rules": {"user_id": user_id, "name": "Forged", "topics": []},
            "notification_queue": {
                "user_id": user_id,
                "rule_id": self.rules[owner]["id"],
                "report_id": self.report["id"],
            },
            "notification_history": self.history_row(user_id),
        }
        return rows[table]

    def select(self, client: Client, table: str) -> list[dict[str, Any]]:
        return response_rows(client.table(table).select("*").execute())

    def insert(
        self, client: Client, table: str, owner: str = "alice"
    ) -> list[dict[str, Any]]:
        """Insert ``new_row(table, owner)`` through ``client``; the stored rows."""
        return response_rows(
            client.table(table).insert(self.new_row(table, owner)).execute()
        )

    def forge(self, client: Client, table: str, owner: str = "alice") -> None:
        """Insert ``new_row(table, owner)`` through ``client`` without reading it back.

        With nothing returned, no SELECT policy is involved: only the table's
        INSERT policy can refuse the row.
        """
        client.table(table).insert(
            self.new_row(table, owner), returning=ReturnMethod.minimal
        ).execute()

    def assert_writes_change_nothing(self, client: Client, table: str) -> None:
        """Updates and deletes through ``client`` leave ``table`` as it was."""
        before = self.rows(table)
        column = WRITABLE_COLUMNS.get(table, "created_at")
        value = "Renamed" if column == "name" else "2020-01-01T00:00:00+00:00"
        self.assertEqual(
            client.table(table)
            .update({column: value})
            .neq(column, value)
            .execute()
            .data,
            [],
        )
        client.table(table).delete().neq(column, value).execute()
        self.assertEqual(self.rows(table), before)


class TestAnonKey(RowLevelSecurityTestCase):
    def setUp(self) -> None:
        self.anon = self.anon_client()

    def test_reads_sources_and_newsletters_only(self) -> None:
        for table in ALL_TABLES:
            with self.subTest(table=table):
                expected = len(self.rows(table)) if table in PUBLIC_TABLES else 0
                self.assertEqual(len(self.select(self.anon, table)), expected)

    def test_cannot_insert_anywhere(self) -> None:
        for table in ALL_TABLES:
            with self.subTest(table=table):
                self.assert_api_error(
                    RLS_VIOLATION, partial(self.forge, self.anon, table)
                )

    def test_cannot_update_or_delete_anything(self) -> None:
        for table in ALL_TABLES:
            with self.subTest(table=table):
                self.assert_writes_change_nothing(self.anon, table)

    def test_search_timeline_is_callable(self) -> None:
        result = self.anon.rpc("search_term_timeline", {"search_query": "x"}).execute()
        self.assertEqual(result.data, [])


class TestUserJwt(RowLevelSecurityTestCase):
    alice: ClassVar[Client]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.alice = cls.user_client("alice@example.test")

    def test_sees_public_tables_and_only_their_own_rows(self) -> None:
        for table in ALL_TABLES:
            with self.subTest(table=table):
                rows = self.select(self.alice, table)
                if table in PUBLIC_TABLES:
                    self.assertEqual(len(rows), len(self.rows(table)))
                elif table in PRIVATE_TABLES:
                    self.assertEqual(rows, [])
                else:
                    owners = {row[PER_USER_TABLES[table]] for row in rows}
                    self.assertEqual(owners, {self.users["alice"]})

    def test_edits_their_own_profile_and_rules_only(self) -> None:
        alice, bob = self.users["alice"], self.users["bob"]
        preferences = {"enabled": False, "delivery_frequency": "daily"}
        cases: list[tuple[str, str, str, dict[str, Any]]] = [
            ("user_profiles", alice, bob, {"notification_preferences": preferences}),
            (
                "notification_rules",
                self.rules["alice"]["id"],
                self.rules["bob"]["id"],
                {"name": "Mine"},
            ),
        ]
        for table, own_id, other_id, change in cases:
            with self.subTest(table=table):
                updated = (
                    self.alice.table(table).update(change).eq("id", own_id).execute()
                )
                self.assertEqual(len(updated.data), 1)
                others = (
                    self.alice.table(table).update(change).eq("id", other_id).execute()
                )
                self.assertEqual(others.data, [])
                (other_row,) = self.rows(table, id=other_id)
                self.assertNotEqual({key: other_row[key] for key in change}, change)

    def test_creates_and_deletes_only_their_own_rules(self) -> None:
        (created,) = self.insert(self.alice, "notification_rules")
        self.alice.table("notification_rules").delete().eq(
            "id", created["id"]
        ).execute()
        self.assertEqual(self.rows("notification_rules", id=created["id"]), [])

        self.assert_api_error(
            RLS_VIOLATION,
            partial(self.forge, self.alice, "notification_rules", owner="bob"),
        )
        self.alice.table("notification_rules").delete().eq(
            "id", self.rules["bob"]["id"]
        ).execute()
        self.assertEqual(
            len(self.rows("notification_rules", id=self.rules["bob"]["id"])), 1
        )

    def test_cannot_write_content_queue_history_or_reports(self) -> None:
        for table in (
            *PUBLIC_TABLES,
            *PRIVATE_TABLES,
            "notification_queue",
            "notification_history",
        ):
            with self.subTest(table=table):
                self.assert_api_error(
                    RLS_VIOLATION, partial(self.forge, self.alice, table)
                )
                self.assert_writes_change_nothing(self.alice, table)


class TestServiceKey(RowLevelSecurityTestCase):
    def test_reads_every_row_of_every_table(self) -> None:
        expected = {
            "sources": 1,
            "newsletters": 1,
            "email_source_mappings": 1,
            "weekly_topic_reports": 1,
            "user_profiles": 2,
            "notification_rules": 2,
            "notification_queue": 2,
            "notification_history": 2,
        }
        for table, count in expected.items():
            with self.subTest(table=table):
                self.assertEqual(len(self.select(self.db, table)), count)

    def test_writes_every_table(self) -> None:
        for table in ALL_TABLES:
            if table == "user_profiles":
                continue  # one per auth user: the trigger already wrote it
            with self.subTest(table=table):
                self.assertEqual(len(self.insert(self.db, table)), 1)
        self.db.table("user_profiles").update({"email": "renamed@example.test"}).eq(
            "id", self.users["bob"]
        ).execute()
        (bob,) = self.rows("user_profiles", id=self.users["bob"])
        self.assertEqual(bob["email"], "renamed@example.test")


class TestWritePoliciesAlone(RowLevelSecurityTestCase):
    """Each UPDATE and DELETE policy refuses other users' rows by itself.

    Through the API a filter makes the SELECT policy hide those rows first, so
    these statements run in SQL as alice, unfiltered, and are rolled back.
    """

    def rows_alice_changes(self, statement: str) -> int:
        abort_unless_local_postgres(self.stack.db_url)
        claims = json.dumps({"sub": self.users["alice"], "role": "authenticated"})
        with psycopg.connect(self.stack.db_url) as connection:
            connection.execute("SET LOCAL ROLE authenticated")
            connection.execute(
                "SELECT set_config('request.jwt.claims', %s, true)", (claims,)
            )
            changed = connection.execute(statement.encode()).rowcount
            connection.rollback()
        return changed

    def test_alice_changes_only_her_own_rows(self) -> None:
        for statement in (
            "UPDATE notification_rules SET name = 'Renamed'",
            "DELETE FROM notification_rules",
            "UPDATE user_profiles SET email = 'renamed@example.test'",
        ):
            with self.subTest(statement=statement):
                self.assertEqual(self.rows_alice_changes(statement), 1)
