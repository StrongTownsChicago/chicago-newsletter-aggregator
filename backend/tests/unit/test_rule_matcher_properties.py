"""Property-based tests for notification rule matching against a reference model."""

import unittest
from typing import Any
from unittest.mock import Mock, patch

from hypothesis import given
from hypothesis import strategies as st

from notifications.rule_matcher import (
    _rule_matches_newsletter,
    match_newsletter_to_rules,
)
from tests.fixtures.mock_helpers import create_mock_supabase
from tests.fixtures.property_settings import PROPERTY_SETTINGS

TOPICS = ["bike_lanes", "zoning", "transit", "housing"]
WARDS = ["1", "2", "40"]
# ASCII words keep "case-insensitive" unambiguous (str.lower and casefold agree).
WORDS = ["bike", "Lane", "ZONING", "park", "the"]

TOPIC_LISTS = st.one_of(st.none(), st.lists(st.sampled_from(TOPICS), max_size=3))
WARD_LISTS = st.one_of(st.none(), st.lists(st.sampled_from(WARDS), max_size=2))
TEXTS = st.lists(st.sampled_from(WORDS), max_size=6).map(" ".join)


@st.composite
def rules(draw: st.DrawFn) -> dict[str, Any]:
    """Rules as the database returns them; filters may be missing, null or empty."""
    rule: dict[str, Any] = {
        "id": draw(st.uuids()).hex,
        "user_id": draw(st.sampled_from(["user1", "user2", "user3"])),
        "name": "Rule",
    }
    optional_fields = {
        "topics": TOPIC_LISTS,
        "search_term": st.one_of(st.none(), st.just(""), TEXTS),
        "ward_numbers": WARD_LISTS,
    }
    for field, values in optional_fields.items():
        if draw(st.booleans()):
            rule[field] = draw(values)
    return rule


NEWSLETTERS = st.fixed_dictionaries(
    {},
    optional={
        "topics": TOPIC_LISTS,
        "plain_text": st.one_of(st.none(), TEXTS),
        "ward_number": st.one_of(st.none(), st.sampled_from(WARDS)),
    },
)


def reference_matches(rule: dict[str, Any], newsletter: dict[str, Any]) -> bool:
    """The documented rule semantics: filters AND-ed, values within one OR-ed,
    and a filter that is missing, null or empty places no constraint."""
    rule_topics = rule.get("topics") or []
    search_term = rule.get("search_term") or ""
    rule_wards = rule.get("ward_numbers") or []
    newsletter_topics = newsletter.get("topics") or []
    text = newsletter.get("plain_text") or ""

    topics_match = not rule_topics or any(t in newsletter_topics for t in rule_topics)
    term_matches = not search_term or search_term.lower() in text.lower()
    ward_matches = not rule_wards or newsletter.get("ward_number") in rule_wards
    return topics_match and term_matches and ward_matches


class TestRuleMatchingProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(rules(), NEWSLETTERS)
    def test_agrees_with_the_reference_model(
        self, rule: dict[str, Any], newsletter: dict[str, Any]
    ) -> None:
        self.assertEqual(
            _rule_matches_newsletter(rule, newsletter),
            reference_matches(rule, newsletter),
        )

    @PROPERTY_SETTINGS
    @given(rules(), NEWSLETTERS, st.sampled_from(TOPICS))
    def test_a_newsletter_with_more_topics_still_matches(
        self, rule: dict[str, Any], newsletter: dict[str, Any], extra_topic: str
    ) -> None:
        if not _rule_matches_newsletter(rule, newsletter):
            return
        widened = {
            **newsletter,
            "topics": [*(newsletter.get("topics") or []), extra_topic],
        }
        self.assertTrue(_rule_matches_newsletter(rule, widened))

    @PROPERTY_SETTINGS
    @given(
        st.lists(rules(), max_size=5),
        # A user's "enabled" preference: None when never set; absent users have no profile.
        st.dictionaries(
            st.sampled_from(["user1", "user2", "user3"]),
            st.one_of(st.none(), st.booleans()),
        ),
        NEWSLETTERS,
    )
    def test_returns_matching_rules_of_enabled_users_in_order(
        self,
        active_rules: list[dict[str, Any]],
        enabled_by_user: dict[str, bool | None],
        newsletter: dict[str, Any],
    ) -> None:
        profiles = [
            {
                "id": user,
                "notification_preferences": {}
                if enabled is None
                else {"enabled": enabled},
            }
            for user, enabled in enabled_by_user.items()
        ]
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.side_effect = [
            Mock(data=active_rules),
            Mock(data=profiles),
        ]

        # Patched per example: @patch decorators can't sit under @given.
        with (
            patch(
                "notifications.rule_matcher.get_supabase_client",
                return_value=mock_supabase,
            ),
            patch("builtins.print"),
        ):
            result = match_newsletter_to_rules("newsletter_id", newsletter)

        def is_notified(user: str) -> bool:
            return user in enabled_by_user and enabled_by_user[user] is not False

        expected = [
            rule["id"]
            for rule in active_rules
            if is_notified(rule["user_id"]) and reference_matches(rule, newsletter)
        ]
        self.assertEqual([match["rule_id"] for match in result], expected)


if __name__ == "__main__":
    unittest.main()
