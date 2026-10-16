"""Unit tests for Pydantic models."""

import unittest
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from models import (
    EmailSourceMapping,
    Newsletter,
    NewsletterCreate,
    NewsletterMatching,
    NewsletterProcessing,
    NotificationQueueEntry,
    NotificationRule,
    RuleMatch,
    Source,
    UserProfile,
)


class TestNewsletterModels(unittest.TestCase):
    """Tests for Newsletter Pydantic models."""

    def test_newsletter_create_minimal_valid(self) -> None:
        """Newsletter with only required fields."""
        newsletter = NewsletterCreate(
            subject="Test Newsletter", plain_text="Test content"
        )

        self.assertEqual(newsletter.subject, "Test Newsletter")
        self.assertEqual(newsletter.plain_text, "Test content")
        self.assertIsNone(newsletter.raw_html)
        self.assertEqual(newsletter.topics, [])  # Default value

    def test_newsletter_create_full_valid(self) -> None:
        """Newsletter with all optional fields."""
        newsletter = NewsletterCreate(
            subject="Test Newsletter",
            plain_text="Test content",
            raw_html="<p>Test</p>",
            email_uid="test-123",
            received_date=datetime(2026, 1, 30, 10, 0, 0),
            from_email="test@example.com",
            to_email="recipient@example.com",
            source_id="source-456",
            topics=["bike_lanes", "transit_funding"],
            summary="Test summary",
        )

        self.assertEqual(newsletter.subject, "Test Newsletter")
        self.assertEqual(newsletter.plain_text, "Test content")
        self.assertEqual(newsletter.raw_html, "<p>Test</p>")
        self.assertEqual(newsletter.email_uid, "test-123")
        self.assertEqual(newsletter.source_id, "source-456")
        self.assertEqual(newsletter.topics, ["bike_lanes", "transit_funding"])
        self.assertEqual(newsletter.summary, "Test summary")

    def test_newsletter_with_id_from_db(self) -> None:
        """Newsletter model includes ID after DB fetch."""
        newsletter = Newsletter(
            id="uuid-123",
            subject="Test",
            plain_text="Content",
            created_at=datetime(2026, 1, 30, 10, 0, 0),
        )

        self.assertEqual(newsletter.id, "uuid-123")
        self.assertIsInstance(newsletter.created_at, datetime)

    def test_newsletter_strips_whitespace(self) -> None:
        """Subject whitespace automatically stripped."""
        newsletter = NewsletterCreate(
            subject="  Test Newsletter  ", plain_text="Content"
        )

        self.assertEqual(newsletter.subject, "Test Newsletter")

    def test_newsletter_empty_subject_fails(self) -> None:
        """Empty subject raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            NewsletterCreate(subject="", plain_text="Content")

        error = ctx.exception
        self.assertIn("subject", str(error))

    def test_newsletter_missing_plain_text_fails(self) -> None:
        """Missing required field raises error."""
        with self.assertRaises(ValidationError):
            NewsletterCreate(subject="Test")  # deliberately missing fields

    def test_newsletter_ignores_legacy_relevance_score_column(self) -> None:
        """Deprecated relevance_score in database rows is ignored, even if out of range."""
        newsletter = NewsletterCreate.model_validate(
            {"subject": "Test", "plain_text": "Content", "relevance_score": 11}
        )

        self.assertFalse(hasattr(newsletter, "relevance_score"))

    def test_newsletter_topics_default_empty_list(self) -> None:
        """Topics defaults to empty list, not None."""
        newsletter = NewsletterCreate(subject="Test", plain_text="Content")

        self.assertEqual(newsletter.topics, [])
        self.assertIsInstance(newsletter.topics, list)

    def test_newsletter_model_dump(self) -> None:
        """model_dump() returns dict for DB insertion."""
        newsletter = NewsletterCreate(
            subject="Test",
            plain_text="Content",
            email_uid="test-123",
            topics=["bike_lanes"],
        )

        data = newsletter.model_dump()

        self.assertIsInstance(data, dict)
        self.assertEqual(data["subject"], "Test")
        self.assertEqual(data["plain_text"], "Content")
        self.assertEqual(data["email_uid"], "test-123")
        self.assertEqual(data["topics"], ["bike_lanes"])

    def test_newsletter_model_validate(self) -> None:
        """model_validate() creates model from dict."""
        data = {
            "subject": "Test",
            "plain_text": "Content",
            "email_uid": "test-123",
            "topics": ["bike_lanes"],
        }

        newsletter = NewsletterCreate.model_validate(data)

        self.assertIsInstance(newsletter, NewsletterCreate)
        self.assertEqual(newsletter.subject, "Test")
        self.assertEqual(newsletter.topics, ["bike_lanes"])

    def test_newsletter_matching_defaults(self) -> None:
        """NewsletterMatching has sensible defaults."""
        matching = NewsletterMatching()

        self.assertEqual(matching.topics, [])
        self.assertEqual(matching.plain_text, "")
        self.assertIsNone(matching.source_id)
        self.assertIsNone(matching.ward_number)

    def test_newsletter_processing_minimal(self) -> None:
        """NewsletterProcessing only needs subject + plain_text."""
        processing = NewsletterProcessing(subject="Test", plain_text="Content")

        self.assertEqual(processing.subject, "Test")
        self.assertEqual(processing.plain_text, "Content")

    def test_newsletter_with_null_values(self) -> None:
        """NULL database values handled correctly."""
        db_data: dict[str, Any] = {
            "subject": "Test",
            "plain_text": "Content",
            "raw_html": None,
            "source_id": None,
            "ward_number": None,
            "topics": [],
            "summary": None,
        }

        newsletter = NewsletterCreate.model_validate(db_data)

        self.assertIsNone(newsletter.raw_html)
        self.assertIsNone(newsletter.source_id)
        self.assertEqual(newsletter.topics, [])

    def test_empty_string_vs_none(self) -> None:
        """Empty string vs None handled differently."""
        # None is allowed for optional fields
        newsletter1 = NewsletterCreate(
            subject="Test", plain_text="Content", raw_html=None
        )
        self.assertIsNone(newsletter1.raw_html)

        # Empty string is not stripped to None
        newsletter2 = NewsletterCreate(
            subject="Test", plain_text="Content", raw_html=""
        )
        self.assertEqual(newsletter2.raw_html, "")


class TestSourceModels(unittest.TestCase):
    """Tests for Source Pydantic models."""

    def test_source_valid_alderman(self) -> None:
        """Alderman source with ward number."""
        source = Source(
            id="source-123",
            name="Alderman Smith",
            ward_number=1,
            source_type="alderman",
            is_active=True,
        )

        self.assertEqual(source.name, "Alderman Smith")
        self.assertEqual(source.ward_number, 1)
        self.assertEqual(source.source_type, "alderman")

    def test_source_valid_other(self) -> None:
        """Non-alderman source without ward."""
        source = Source(
            id="source-456",
            name="Chicago Transit Authority",
            ward_number=None,
            source_type="other",
        )

        self.assertEqual(source.name, "Chicago Transit Authority")
        self.assertIsNone(source.ward_number)
        self.assertTrue(source.is_active)  # Default value

    def test_source_empty_name_fails(self) -> None:
        """Empty name raises error."""
        with self.assertRaises(ValidationError) as ctx:
            Source(id="test", name="", source_type="alderman")

        error = ctx.exception
        self.assertIn("name", str(error))

    def test_source_ward_in_range(self) -> None:
        """Ward 1-50 accepted."""
        # Valid boundaries
        Source(id="1", name="Ward 1", ward_number=1, source_type="alderman")
        Source(id="50", name="Ward 50", ward_number=50, source_type="alderman")

        # Valid middle
        Source(id="25", name="Ward 25", ward_number=25, source_type="alderman")

    def test_source_ward_out_of_range(self) -> None:
        """Ward 0, 51+ rejected."""
        # Ward 0
        with self.assertRaises(ValidationError):
            Source(id="0", name="Ward 0", ward_number=0, source_type="alderman")

        # Ward 51
        with self.assertRaises(ValidationError):
            Source(id="51", name="Ward 51", ward_number=51, source_type="alderman")

        # Ward 100
        with self.assertRaises(ValidationError):
            Source(
                id="100",
                name="Ward 100",
                ward_number=100,
                source_type="alderman",
            )

    def test_email_mapping_valid(self) -> None:
        """Email mapping with pattern and source_id."""
        mapping = EmailSourceMapping(
            id=1, email_pattern="%@example.com", source_id="source-123"
        )

        self.assertEqual(mapping.id, 1)
        self.assertEqual(mapping.email_pattern, "%@example.com")
        self.assertEqual(mapping.source_id, "source-123")

    def test_email_mapping_empty_pattern_fails(self) -> None:
        """Empty email pattern rejected."""
        with self.assertRaises(ValidationError) as ctx:
            EmailSourceMapping(id=1, email_pattern="", source_id="source-123")

        error = ctx.exception
        self.assertIn("email_pattern", str(error))


class TestNotificationModels(unittest.TestCase):
    """Tests for Notification Pydantic models."""

    def test_notification_rule_minimal(self) -> None:
        """Rule with just required fields."""
        rule = NotificationRule(id="rule-123", user_id="user-456", name="My Rule")

        self.assertEqual(rule.id, "rule-123")
        self.assertEqual(rule.user_id, "user-456")
        self.assertEqual(rule.name, "My Rule")
        self.assertEqual(rule.topics, [])  # Default
        self.assertIsNone(rule.search_term)
        self.assertEqual(rule.source_ids, [])  # Default
        self.assertEqual(rule.ward_numbers, [])  # Default
        self.assertTrue(rule.is_active)  # Default

    def test_notification_rule_full(self) -> None:
        """Rule with all filters."""
        rule = NotificationRule(
            id="rule-123",
            user_id="user-456",
            name="Bike Lane Notifications",
            topics=["bike_lanes", "pedestrian_infrastructure"],
            search_term="cycling",
            source_ids=["source-1", "source-2"],
            ward_numbers=[1, 2, 3],
            is_active=True,
        )

        self.assertEqual(rule.topics, ["bike_lanes", "pedestrian_infrastructure"])
        self.assertEqual(rule.search_term, "cycling")
        self.assertEqual(rule.source_ids, ["source-1", "source-2"])
        self.assertEqual(rule.ward_numbers, [1, 2, 3])

    def test_notification_rule_empty_name_fails(self) -> None:
        """Empty rule name rejected."""
        with self.assertRaises(ValidationError) as ctx:
            NotificationRule(id="rule-123", user_id="user-456", name="")

        error = ctx.exception
        self.assertIn("name", str(error))

    def test_notification_rule_topics_default_empty(self) -> None:
        """Topics default to empty list."""
        rule = NotificationRule(id="rule-123", user_id="user-456", name="Test")

        self.assertEqual(rule.topics, [])
        self.assertIsInstance(rule.topics, list)

    def test_notification_rule_ignores_legacy_min_relevance_score(self) -> None:
        """Deprecated min_relevance_score in database rows is ignored."""
        rule = NotificationRule.model_validate(
            {
                "id": "rule-123",
                "user_id": "user-456",
                "name": "Test",
                "min_relevance_score": 11,
            }
        )

        self.assertFalse(hasattr(rule, "min_relevance_score"))

    def test_rule_match_valid(self) -> None:
        """RuleMatch with all required fields."""
        match = RuleMatch(user_id="user-123", rule_id="rule-456", rule_name="Test Rule")

        self.assertEqual(match.user_id, "user-123")
        self.assertEqual(match.rule_id, "rule-456")
        self.assertEqual(match.rule_name, "Test Rule")

    def test_notification_queue_entry_valid(self) -> None:
        """Queue entry with all fields."""
        entry = NotificationQueueEntry(
            id="notif-123",
            user_id="user-123",
            newsletter_id="newsletter-456",
            rule_id="rule-789",
            status="pending",
            digest_batch_id="2026-01-30",
            created_at=datetime(2026, 1, 30, 10, 0, 0),
        )

        self.assertEqual(entry.id, "notif-123")
        self.assertEqual(entry.user_id, "user-123")
        self.assertEqual(entry.newsletter_id, "newsletter-456")
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.digest_batch_id, "2026-01-30")

    def test_notification_queue_entry_status_valid(self) -> None:
        """Status must be pending/sent/failed."""
        for status in ["pending", "sent", "failed"]:
            entry = NotificationQueueEntry(
                id="notif-123",
                user_id="user-123",
                newsletter_id="newsletter-456",
                rule_id="rule-789",
                status=status,
                digest_batch_id="2026-01-30",
                created_at=datetime.now(),
            )
            self.assertEqual(entry.status, status)

    def test_notification_queue_entry_status_invalid(self) -> None:
        """Invalid status rejected."""
        with self.assertRaises(ValidationError) as ctx:
            NotificationQueueEntry(
                id="notif-123",
                user_id="user-123",
                newsletter_id="newsletter-456",
                rule_id="rule-789",
                status="invalid",
                digest_batch_id="2026-01-30",
                created_at=datetime.now(),
            )

        error = ctx.exception
        self.assertIn("status", str(error))

    def test_user_profile_valid_email(self) -> None:
        """User with valid email."""
        profile = UserProfile(id="user-123", email="test@example.com")

        self.assertEqual(profile.id, "user-123")
        self.assertEqual(profile.email, "test@example.com")

    def test_user_profile_invalid_email(self) -> None:
        """Invalid email rejected."""
        invalid_emails = ["not-an-email", "@example.com", "test@", "test"]

        for invalid_email in invalid_emails:
            with self.assertRaises(ValidationError):
                UserProfile(id="user-123", email=invalid_email)

    def test_user_profile_preferences_default(self) -> None:
        """Notification preferences default to enabled and daily."""
        profile = UserProfile(id="user-123", email="test@example.com")

        self.assertEqual(
            profile.notification_preferences,
            {"enabled": True, "delivery_frequency": "daily"},
        )


class TestEdgeCases(unittest.TestCase):
    """Edge case validation tests."""

    def test_newsletter_with_invalid_type(self) -> None:
        """Invalid type raises clear error."""
        with self.assertRaises(ValidationError) as ctx:
            NewsletterCreate(
                subject=123,  # deliberately wrong type
                plain_text="Content",
            )

        error = ctx.exception
        error_str = str(error)
        self.assertIn("subject", error_str)
        self.assertIn("string", error_str.lower())

    def test_source_ward_boundary_values(self) -> None:
        """Ward number boundary validation."""
        # Valid boundaries
        Source(id="1", name="Ward 1", ward_number=1, source_type="alderman")
        Source(id="50", name="Ward 50", ward_number=50, source_type="alderman")

        # Invalid boundaries
        with self.assertRaises(ValidationError):
            Source(id="0", name="Ward 0", ward_number=0, source_type="alderman")

        with self.assertRaises(ValidationError):
            Source(id="51", name="Ward 51", ward_number=51, source_type="alderman")

    def test_date_parsing(self) -> None:
        """Dates parsed from ISO strings."""
        db_data = {
            "id": "test",
            "subject": "Test",
            "plain_text": "Content",
            "received_date": "2026-01-30T15:30:00Z",
        }

        newsletter = Newsletter.model_validate(db_data)

        self.assertIsInstance(newsletter.received_date, datetime)
        self.assertEqual(newsletter.received_date.year, 2026)
        self.assertEqual(newsletter.received_date.month, 1)
        self.assertEqual(newsletter.received_date.day, 30)


if __name__ == "__main__":
    unittest.main()
