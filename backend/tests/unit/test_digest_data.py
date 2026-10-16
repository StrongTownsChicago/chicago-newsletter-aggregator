"""Unit tests for notifications/digest_data.py digest data preparation."""

import unittest
from typing import Any

from notifications.digest_data import prepare_newsletter_data
from tests.fixtures.newsletter_factory import create_test_newsletter, create_test_source


class TestPrepareNewsletterData(unittest.TestCase):
    """Tests for prepare_newsletter_data() function."""

    def test_groups_by_newsletter(self) -> None:
        """Multiple rules matching same newsletter are grouped."""
        newsletter = create_test_newsletter(id="nl_123", subject="Test Newsletter")

        notifications = [
            {
                "newsletter": newsletter,
                "rule": {"name": "Rule 1"},
            },
            {
                "newsletter": newsletter,
                "rule": {"name": "Rule 2"},
            },
        ]

        result = prepare_newsletter_data(notifications)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["matched_rules"]), 2)
        self.assertIn("Rule 1", result[0]["matched_rules"])
        self.assertIn("Rule 2", result[0]["matched_rules"])

    def test_extracts_source_info(self) -> None:
        """Source name and ward number extracted correctly."""
        source = create_test_source(source_id=1, name="Test Alderman", ward_number=25)
        newsletter = create_test_newsletter(source_id=1)
        newsletter["source"] = source

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["source_name"], "Test Alderman")
        self.assertEqual(result[0]["ward_text"], " (Ward 25)")

    def test_formats_date(self) -> None:
        """ISO format date converted to readable format."""
        newsletter = create_test_newsletter(received_date="2026-01-24T12:30:00+00:00")

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["date_formatted"], "January 24, 2026")

    def test_handles_missing_date(self) -> None:
        """Missing date defaults to 'Unknown date'."""
        # Use overrides to bypass the factory's default logic
        newsletter = create_test_newsletter()
        newsletter["received_date"] = ""  # Set to empty string after creation

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["date_formatted"], "Unknown date")

    def test_handles_missing_source(self) -> None:
        """Missing source defaults to 'Unknown Source'."""
        newsletter = create_test_newsletter()
        newsletter["source"] = None

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["source_name"], "Unknown Source")
        self.assertEqual(result[0]["ward_text"], "")

    def test_builds_newsletter_url(self) -> None:
        """Newsletter URL constructed with FRONTEND_BASE_URL."""
        newsletter = create_test_newsletter(id="nl_abc123")

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = prepare_newsletter_data(notifications)

        self.assertIn("nl_abc123", result[0]["newsletter_url"])

    def test_sorts_by_received_date(self) -> None:
        """Newsletters sorted by received date, most recent first."""
        newsletter1 = create_test_newsletter(
            id="nl_1", received_date="2026-01-24T10:00:00"
        )
        newsletter2 = create_test_newsletter(
            id="nl_2", received_date="2026-01-24T14:00:00"
        )

        notifications = [
            {"newsletter": newsletter1, "rule": {"name": "Rule 1"}},
            {"newsletter": newsletter2, "rule": {"name": "Rule 1"}},
        ]

        result = prepare_newsletter_data(notifications)

        # Most recent should be first
        self.assertIn("nl_2", result[0]["newsletter_url"])
        self.assertIn("nl_1", result[1]["newsletter_url"])

    def test_collects_matched_rules(self) -> None:
        """Rule names collected for each newsletter."""
        newsletter = create_test_newsletter()

        notifications = [
            {"newsletter": newsletter, "rule": {"name": "Zoning Updates"}},
            {"newsletter": newsletter, "rule": {"name": "Bike Lanes"}},
        ]

        result = prepare_newsletter_data(notifications)

        self.assertIn("Zoning Updates", result[0]["matched_rules"])
        self.assertIn("Bike Lanes", result[0]["matched_rules"])

    def test_empty_notifications_returns_empty(self) -> None:
        """Empty notifications list returns empty result."""
        result = prepare_newsletter_data([])

        self.assertEqual(result, [])

    def test_handles_malformed_notifications(self) -> None:
        """Malformed notifications are skipped without error."""
        notifications: list[dict[str, Any]] = [
            {"newsletter": None},  # Missing newsletter
            {"newsletter": {"id": None}},  # Missing ID
            {"something": "else"},  # Totally wrong structure
        ]
        result = prepare_newsletter_data(notifications)
        self.assertEqual(result, [])

    def test_handles_invalid_date_format(self) -> None:
        """Invalid date format falls back to substring."""
        newsletter = create_test_newsletter(received_date="2026-01-24-INVALID")
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = prepare_newsletter_data(notifications)
        # Should take first 10 chars as fallback
        self.assertEqual(result[0]["date_formatted"], "2026-01-24")
