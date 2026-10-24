"""SQL functions and full-text search, with known inputs and known outputs."""

from datetime import date, timedelta
from typing import Any, ClassVar

from tests.db_integration.local_supabase import (
    TEST_PASSWORD,
    LocalSupabaseTestCase,
    response_rows,
)
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source
from tests.fixtures.user_factory import create_auth_user, insert_rule

INVALID_PARAMETER_VALUE = "22023"
#: SEARCH_TIMELINE_MAX_QUERY_LENGTH in frontend/src/lib/search-timeline.ts.
MAX_TIMELINE_QUERY = 200


class TestRuleFunctions(LocalSupabaseTestCase):
    user_id: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_id = create_auth_user(cls.db, "counted@example.test", TEST_PASSWORD)
        other_id = create_auth_user(cls.db, "other@example.test", TEST_PASSWORD)
        weekly = {"delivery_frequency": "weekly"}
        insert_rule(cls.db, cls.user_id, topics=["bike_lanes", "city_budget"], **weekly)
        insert_rule(
            cls.db, cls.user_id, topics=["tax_policy"], **weekly, is_active=False
        )
        insert_rule(cls.db, cls.user_id, topics=["transit_funding"])
        insert_rule(cls.db, other_id, topics=["bike_lanes", "city_charter"], **weekly)

    def test_count_user_rules_counts_one_users_rules(self) -> None:
        count = self.db.rpc("count_user_rules", {"user_uuid": self.user_id}).execute()
        self.assertEqual(count.data, 3)

    def test_active_weekly_topics_are_distinct_and_skip_inactive_and_daily(
        self,
    ) -> None:
        rows = response_rows(self.db.rpc("get_active_weekly_topics").execute())

        self.assertCountEqual(
            [row["topic"] for row in rows],
            ["bike_lanes", "city_budget", "city_charter"],
        )


class TestWeekDateRange(LocalSupabaseTestCase):
    def week_range(self, week_id: str) -> tuple[str, str]:
        (row,) = response_rows(
            self.db.rpc("get_week_date_range", {"week_id_param": week_id}).execute()
        )
        return row["week_start"], row["week_end"]

    def test_matches_iso_weeks_across_year_boundaries_and_dst_changes(self) -> None:
        for year, week in (
            (2026, 1),  # starts in 2025
            (2020, 53),  # ends in 2021
            (2026, 10),  # Sunday 8 March: DST starts
            (2026, 44),  # Sunday 1 November: DST ends
            (2027, 52),
        ):
            week_id = f"{year}-W{week:02d}"
            with self.subTest(week_id=week_id):
                monday = date.fromisocalendar(year, week, 1)
                self.assertEqual(
                    self.week_range(week_id),
                    (monday.isoformat(), (monday + timedelta(days=6)).isoformat()),
                )


class TestFullTextSearch(LocalSupabaseTestCase):
    """Zoning newsletters across months and wards, as /search sees them."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        ward_1 = insert_source(cls.db, name="Ward 1 Office", ward_number=1)["id"]
        ward_2 = insert_source(cls.db, name="Ward 2 Office", ward_number=2)["id"]
        for source_id, received, subject, text in (
            (ward_1, "2026-01-10T15:00:00+00:00", "Zoning update", "Hearing."),
            (ward_2, "2026-01-20T15:00:00+00:00", "Ward news", "A zoned lot."),
            (ward_1, "2026-02-05T15:00:00+00:00", "Ward news", "Rezoning talk."),
            # 9pm on 28 February in Chicago, already March in UTC.
            (ward_2, "2026-03-01T03:00:00+00:00", "Zoning board", "Agenda."),
            (ward_1, "2026-03-10T15:00:00+00:00", "Snow plows", "Salt trucks."),
        ):
            insert_newsletter(
                cls.db,
                source_id,
                received_date=received,
                subject=subject,
                plain_text=text,
            )

    def search(self, query: str) -> list[dict[str, Any]]:
        return response_rows(
            self.db.table("newsletters")
            .select("subject, plain_text")
            .text_search(
                "search_vector",
                query,
                options={"type": "web_search", "config": "english"},
            )
            .execute()
        )

    def timeline(self, query: str) -> list[dict[str, Any]]:
        return response_rows(
            self.db.rpc("search_term_timeline", {"search_query": query}).execute()
        )

    def test_matches_subject_and_body_with_english_stemming(self) -> None:
        # "zoning" and "zoned" share the stem "zone"; "rezoning" does not.
        self.assertEqual(len(self.search("zoning")), 3)
        self.assertEqual(len(self.search("zoned")), 3)
        self.assertEqual(len(self.search("rezoning")), 1)
        self.assertEqual(len(self.search("zoning -board")), 2)

    def test_timeline_counts_chicago_months_and_wards(self) -> None:
        self.assertEqual(
            self.timeline("zoning"),
            [
                {"month": "2026-01-01", "newsletter_count": 2, "ward_count": 2},
                {"month": "2026-02-01", "newsletter_count": 1, "ward_count": 1},
            ],
        )

    def test_timeline_months_sum_to_the_search_count(self) -> None:
        for query in ("zoning", "rezoning", "salt OR agenda", '"zoning update"'):
            with self.subTest(query=query):
                self.assertEqual(
                    sum(row["newsletter_count"] for row in self.timeline(query)),
                    len(self.search(query)),
                )

    def test_timeline_rejects_an_empty_query(self) -> None:
        self.assert_api_error(INVALID_PARAMETER_VALUE, lambda: self.timeline("  "))

    def test_timeline_takes_up_to_200_characters_after_trimming(self) -> None:
        self.assertEqual(self.timeline(f"  {'z' * MAX_TIMELINE_QUERY}  "), [])
        self.assert_api_error(
            INVALID_PARAMETER_VALUE,
            lambda: self.timeline("z" * (MAX_TIMELINE_QUERY + 1)),
        )
