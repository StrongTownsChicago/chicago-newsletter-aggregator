"""Properties of /search's full-text match and the timeline RPC, for generated queries."""

from collections import defaultdict
from datetime import datetime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from hypothesis import given, settings
from hypothesis import strategies as st
from supabase import Client

from tests.db_integration.local_supabase import LocalSupabaseTestCase, response_rows
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source

CHICAGO = ZoneInfo("America/Chicago")
#: Each example is two API calls; fewer than the unit properties' 200 keeps this fast.
DATABASE_PROPERTY_SETTINGS = settings(max_examples=60, deadline=None)

WORDS = ("zoning", "zoned", "budget", "snow", "plows", "park", "transit", "the")
#: (ward or None, received_date UTC, subject, plain_text). Times near midnight on
#: the first of a month fall in the previous month in Chicago. January has two
#: newsletters from ward 1, so ward counts must count wards, not newsletters.
NEWSLETTERS = (
    ("1", "2026-01-10T15:00:00+00:00", "Zoning update", "The park budget."),
    ("1", "2026-01-24T15:00:00+00:00", "Park cleanup", "Snow on the zoning map."),
    ("2", "2026-02-01T03:00:00+00:00", "Snow plows", "Zoned lots near transit."),
    ("2", "2026-02-14T15:00:00+00:00", "Budget hearing", "Snow and plows."),
    ("1", "2026-03-01T05:30:00+00:00", "Transit news", "Park zoning."),
    (None, "2026-03-20T15:00:00+00:00", "Citywide budget", "Transit and the park."),
    ("3", "2026-04-01T04:59:00+00:00", "Ward 3 notes", "Snow."),
)

word = st.sampled_from(WORDS)
term = st.one_of(
    word,
    word.map(lambda w: f"-{w}"),
    st.lists(word, min_size=1, max_size=3).map(lambda ws: '"' + " ".join(ws) + '"'),
    st.sampled_from(("OR", "or", "-", '"', "&", "|", "!", ":*", "(", ")", "'")),
)
search_query = st.lists(term, min_size=1, max_size=5).map(" ".join)


class TestSearchProperties(LocalSupabaseTestCase):
    wards_by_source: ClassVar[dict[int, str | None]]
    anon: ClassVar[Client]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        sources: dict[str | None, int] = {}
        for ward, received, subject, text in NEWSLETTERS:
            if ward not in sources:
                sources[ward] = insert_source(
                    cls.db,
                    name=f"Office {ward}",
                    ward_number=ward,
                    source_type="alderman" if ward else "city",
                )["id"]
            insert_newsletter(
                cls.db,
                sources[ward],
                received_date=received,
                subject=subject,
                plain_text=text,
            )
        cls.wards_by_source = {source: ward for ward, source in sources.items()}
        cls.anon = cls.anon_client()

    def search(self, query: str) -> list[dict[str, Any]]:
        """Matches as /search filters them (websearch syntax, english config)."""
        return response_rows(
            self.db.table("newsletters")
            .select("received_date, source_id")
            .text_search(
                "search_vector",
                query,
                options={"type": "web_search", "config": "english"},
            )
            .execute()
        )

    def expected_timeline(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The timeline built from /search's own matches: Chicago months, distinct wards."""
        months: dict[str, list[str | None]] = defaultdict(list)
        for match in matches:
            received = datetime.fromisoformat(match["received_date"])
            month = received.astimezone(CHICAGO).date().replace(day=1).isoformat()
            months[month].append(self.wards_by_source[match["source_id"]])
        return [
            {
                "month": month,
                "newsletter_count": len(wards),
                "ward_count": len({ward for ward in wards if ward is not None}),
            }
            for month, wards in sorted(months.items())
        ]

    @DATABASE_PROPERTY_SETTINGS
    @given(search_query)
    def test_timeline_is_the_search_results_by_chicago_month(self, query: str) -> None:
        timeline = response_rows(
            self.anon.rpc("search_term_timeline", {"search_query": query}).execute()
        )

        self.assertEqual(timeline, self.expected_timeline(self.search(query)))
