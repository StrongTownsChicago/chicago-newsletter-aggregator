"""Constraints, triggers and cascades the migrations define, on the real schema."""

from datetime import datetime
from functools import partial
from typing import Any

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

CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
NOT_NULL_VIOLATION = "23502"


class SchemaTestCase(LocalSupabaseTestCase):
    """One source, newsletter, user and daily rule, recreated for every test."""

    def setUp(self) -> None:
        self.reset()
        self.source = insert_source(self.db, name="Ward 3 Office", ward_number=3)
        self.newsletter = insert_newsletter(self.db, self.source["id"])
        self.user_id = create_auth_user(self.db, "member@example.test", TEST_PASSWORD)
        self.rule = insert_rule(self.db, self.user_id, topics=["bike_lanes"])

    def queue_row(self, **fields: Any) -> dict[str, Any]:
        defaults = {
            "user_id": self.user_id,
            "rule_id": self.rule["id"],
            "newsletter_id": self.newsletter["id"],
        }
        return insert_notification(self.db, **{**defaults, **fields})

    def delete(self, table: str, row_id: Any) -> None:
        self.db.table(table).delete().eq("id", row_id).execute()

    def weekly_report(self, topic: str = "bike_lanes") -> dict[str, Any]:
        return insert_row(
            self.db,
            "weekly_topic_reports",
            {
                "topic": topic,
                "week_id": "2026-W05",
                "report_summary": "Summary.",
                "newsletter_ids": [self.newsletter["id"]],
            },
        )


class TestUserProfiles(SchemaTestCase):
    def test_sign_up_creates_a_profile_with_the_documented_defaults(self) -> None:
        (profile,) = self.rows("user_profiles", id=self.user_id)

        self.assertEqual(profile["email"], "member@example.test")
        self.assertEqual(
            profile["notification_preferences"],
            {"enabled": True, "delivery_frequency": "daily"},
        )

    def test_updates_refresh_updated_at(self) -> None:
        for table, row_id in (
            ("user_profiles", self.user_id),
            ("notification_rules", self.rule["id"]),
        ):
            with self.subTest(table=table):
                (row,) = response_rows(
                    self.db.table(table)
                    .update({"updated_at": "2020-01-01T00:00:00+00:00"})
                    .eq("id", row_id)
                    .execute()
                )
                updated_at = datetime.fromisoformat(row["updated_at"])
                self.assertGreater(updated_at.year, 2020)


class TestCascades(SchemaTestCase):
    def test_deleting_a_user_removes_their_profile_rules_queue_and_history(
        self,
    ) -> None:
        self.queue_row()
        insert_row(
            self.db,
            "notification_history",
            {
                "user_id": self.user_id,
                "newsletter_ids": [self.newsletter["id"]],
                "rule_ids": [self.rule["id"]],
                "delivery_type": "daily_digest",
                "success": True,
            },
        )

        self.db.auth.admin.delete_user(self.user_id)

        for table in (
            "user_profiles",
            "notification_rules",
            "notification_queue",
            "notification_history",
        ):
            with self.subTest(table=table):
                self.assertEqual(self.rows(table), [])

    def test_deleting_a_newsletter_report_or_rule_removes_its_queue_rows(
        self,
    ) -> None:
        report = self.weekly_report()
        self.queue_row()
        report_row = self.queue_row(newsletter_id=None, report_id=report["id"])

        self.delete("newsletters", self.newsletter["id"])
        self.assertEqual(
            self.rows("notification_queue", "id"), [{"id": report_row["id"]}]
        )

        self.delete("weekly_topic_reports", report["id"])
        self.assertEqual(self.rows("notification_queue"), [])

        self.newsletter = insert_newsletter(self.db, self.source["id"])
        self.queue_row()
        self.delete("notification_rules", self.rule["id"])
        self.assertEqual(self.rows("notification_queue"), [])

    def test_deleting_a_source_removes_its_mappings(self) -> None:
        other = insert_source(self.db, name="Ward 4 Office", ward_number=4)
        insert_email_mapping(self.db, "%@ward4.example.org", other["id"])

        self.delete("sources", other["id"])

        self.assertEqual(self.rows("email_source_mappings"), [])

    def test_a_source_with_newsletters_cannot_be_deleted(self) -> None:
        # source_id is NOT NULL, so ON DELETE SET NULL fails instead.
        self.assert_api_error(
            NOT_NULL_VIOLATION, partial(self.delete, "sources", self.source["id"])
        )


class TestCheckConstraints(SchemaTestCase):
    def test_queue_status_and_type_must_be_known_values(self) -> None:
        for fields in ({"status": "queued"}, {"notification_type": "monthly"}):
            with self.subTest(fields=fields):
                self.assert_api_error(
                    CHECK_VIOLATION, partial(self.queue_row, **fields)
                )

    def test_history_delivery_type_must_be_known(self) -> None:
        self.assert_api_error(
            CHECK_VIOLATION,
            lambda: insert_row(
                self.db,
                "notification_history",
                {
                    "user_id": self.user_id,
                    "newsletter_ids": [],
                    "rule_ids": [],
                    "delivery_type": "hourly_digest",
                    "success": True,
                },
            ),
        )

    def test_rule_delivery_frequency_must_be_known(self) -> None:
        self.assert_api_error(
            CHECK_VIOLATION,
            lambda: insert_rule(self.db, self.user_id, delivery_frequency="monthly"),
        )

    def test_search_term_is_at_most_100_characters(self) -> None:
        insert_rule(self.db, self.user_id, search_term="x" * 100)
        self.assert_api_error(
            CHECK_VIOLATION,
            lambda: insert_rule(self.db, self.user_id, search_term="x" * 101),
        )

    def test_relevance_score_is_between_0_and_10(self) -> None:
        self.assert_api_error(
            CHECK_VIOLATION,
            lambda: insert_newsletter(self.db, self.source["id"], relevance_score=11),
        )

    def test_a_queue_row_references_exactly_one_content_item(self) -> None:
        report = self.weekly_report()
        for fields in (
            {"report_id": report["id"]},
            {"newsletter_id": None},
        ):
            with self.subTest(fields=fields):
                self.assert_api_error(
                    CHECK_VIOLATION, partial(self.queue_row, **fields)
                )

    def test_weekly_rules_cannot_filter_by_ward(self) -> None:
        self.assert_api_error(
            CHECK_VIOLATION,
            lambda: insert_rule(
                self.db, self.user_id, delivery_frequency="weekly", ward_numbers=["3"]
            ),
        )
        insert_rule(self.db, self.user_id, delivery_frequency="weekly", ward_numbers=[])
        insert_rule(
            self.db, self.user_id, delivery_frequency="daily", ward_numbers=["3"]
        )


class TestUniqueness(SchemaTestCase):
    def test_a_notification_is_queued_once_per_user_content_and_rule(self) -> None:
        self.queue_row()
        self.assert_api_error(UNIQUE_VIOLATION, self.queue_row)

        report = self.weekly_report()
        self.queue_row(newsletter_id=None, report_id=report["id"])
        self.assert_api_error(
            UNIQUE_VIOLATION,
            lambda: self.queue_row(newsletter_id=None, report_id=report["id"]),
        )

    def test_one_report_per_topic_per_week_and_upsert_updates_it(self) -> None:
        original = self.weekly_report()
        self.assert_api_error(UNIQUE_VIOLATION, self.weekly_report)

        self.db.table("weekly_topic_reports").upsert(
            {
                "topic": "bike_lanes",
                "week_id": "2026-W05",
                "report_summary": "Revised.",
                "newsletter_ids": [],
            },
            on_conflict="topic,week_id",
        ).execute()

        (stored,) = self.rows("weekly_topic_reports")
        self.assertEqual(stored["id"], original["id"])
        self.assertEqual(stored["report_summary"], "Revised.")

    def test_email_uid_is_unique(self) -> None:
        insert_newsletter(self.db, self.source["id"], email_uid="uid-1")
        self.assert_api_error(
            UNIQUE_VIOLATION,
            lambda: insert_newsletter(self.db, self.source["id"], email_uid="uid-1"),
        )
