"""Rule matching and queueing (notifications.rule_matcher) on real rules and profiles."""

from typing import Any, ClassVar

from notifications.rule_matcher import (
    get_pending_notifications_by_user,
    match_newsletter_to_rules,
    queue_notifications,
)
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source
from tests.fixtures.quiet_logging import quiet_logger
from tests.fixtures.user_factory import (
    create_auth_user,
    insert_notification,
    insert_rule,
)


def setUpModule() -> None:
    quiet_logger("notifications.rule_matcher")


class TestMatchNewsletterToRules(LocalSupabaseTestCase):
    """One reader's rules of each kind, and a reader who turned notifications off."""

    rules: ClassVar[dict[str, str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        reader = create_auth_user(cls.db, "reader@example.test", TEST_PASSWORD)
        muted = create_auth_user(cls.db, "muted@example.test", TEST_PASSWORD)
        cls.db.table("user_profiles").update(
            {"notification_preferences": {"enabled": False}}
        ).eq("id", muted).execute()
        rule_fields: dict[str, dict[str, Any]] = {
            "topics": {"topics": ["bike_lanes", "transit_funding"]},
            "term": {"search_term": "Snow Plow"},
            "wards": {"ward_numbers": ["40", "41"]},
            "all": {
                "topics": ["bike_lanes"],
                "search_term": "plow",
                "ward_numbers": ["40"],
            },
            "inactive": {"is_active": False},
            "weekly": {"topics": ["bike_lanes"], "delivery_frequency": "weekly"},
        }
        cls.rules = {
            name: insert_rule(cls.db, reader, name=name, **fields)["id"]
            for name, fields in rule_fields.items()
        }
        insert_rule(cls.db, muted, name="muted")

    def matched(self, topics: list[str], text: str, ward: str | None) -> set[str]:
        newsletter = {"topics": topics, "plain_text": text, "ward_number": ward}
        return {
            match["rule_name"]
            for match in match_newsletter_to_rules("newsletter-id", newsletter)
        }

    def test_filters_are_anded_and_values_within_a_filter_ored(self) -> None:
        for topics, text, ward, expected in (
            (
                ["bike_lanes"],
                "The snow plow is coming.",
                "40",
                {"topics", "term", "wards", "all"},
            ),
            (["transit_funding"], "Bus service.", "1", {"topics"}),
            ([], "SNOW PLOW update", "41", {"term", "wards"}),
            (["bike_lanes"], "Bike lanes.", "40", {"topics", "wards"}),
            ([], "Nothing relevant.", None, set()),
        ):
            with self.subTest(topics=topics, text=text, ward=ward):
                self.assertEqual(self.matched(topics, text, ward), expected)


class TestQueueing(LocalSupabaseTestCase):
    def setUp(self) -> None:
        self.reset()
        source_id = insert_source(self.db, name="Ward 12 Office", ward_number=12)["id"]
        self.newsletters = [
            insert_newsletter(self.db, source_id, subject=f"Issue {number}")
            for number in range(4)
        ]
        self.users = [
            create_auth_user(self.db, f"user{number}@example.test", TEST_PASSWORD)
            for number in range(2)
        ]
        self.rules = [insert_rule(self.db, user_id) for user_id in self.users]

    def matches(self) -> list[dict[str, Any]]:
        return [
            {"user_id": user_id, "rule_id": rule["id"], "rule_name": rule["name"]}
            for user_id, rule in zip(self.users, self.rules, strict=True)
        ]

    def test_queues_one_pending_row_per_match_and_skips_duplicates(self) -> None:
        newsletter_id = self.newsletters[0]["id"]

        self.assertEqual(queue_notifications(newsletter_id, self.matches()), 2)
        self.assertEqual(queue_notifications(newsletter_id, self.matches()), 0)

        queued = self.rows("notification_queue")
        self.assertEqual(len(queued), 2)
        self.assertEqual({row["status"] for row in queued}, {"pending"})

    def test_pending_notifications_are_grouped_by_user_oldest_first(self) -> None:
        user, other = self.users
        for newsletter, created_at, status, batch in (
            (self.newsletters[2], "2026-10-01T12:00:00+00:00", "pending", "2026-10-01"),
            (self.newsletters[0], "2026-10-01T08:00:00+00:00", "pending", "2026-10-01"),
            (self.newsletters[1], "2026-10-01T10:00:00+00:00", "sent", "2026-10-01"),
            (self.newsletters[3], "2026-09-30T10:00:00+00:00", "pending", "2026-09-30"),
        ):
            insert_notification(
                self.db,
                user_id=user,
                rule_id=self.rules[0]["id"],
                newsletter_id=newsletter["id"],
                status=status,
                digest_batch_id=batch,
                created_at=created_at,
            )
        insert_notification(
            self.db,
            user_id=other,
            rule_id=self.rules[1]["id"],
            newsletter_id=self.newsletters[0]["id"],
            digest_batch_id="2026-10-01",
        )

        pending = get_pending_notifications_by_user("2026-10-01")

        self.assertEqual(set(pending), {user, other})
        self.assertEqual(
            [row["newsletter"]["subject"] for row in pending[user]],
            ["Issue 0", "Issue 2"],
        )
        first = pending[user][0]
        self.assertEqual(
            first["newsletter"]["source"],
            {"name": "Ward 12 Office", "ward_number": "12"},
        )
        self.assertEqual(first["rule"], {"name": self.rules[0]["name"]})
        self.assertEqual(len(get_pending_notifications_by_user()[user]), 3)
