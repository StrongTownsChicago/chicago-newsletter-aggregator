"""
Unit tests for find_unprocessed_emails utility.

Tests stored-UID paging, read-only mailbox fetching, diffing, and TSV formatting.
"""

import unittest
from datetime import datetime
from unittest.mock import Mock

from utils.find_unprocessed_emails import (
    MailboxEmail,
    fetch_mailbox_emails,
    fetch_stored_email_uids,
    find_unprocessed_emails,
    format_tsv_row,
)


def make_email(
    uid: str,
    sender: str = "ward@example.org",
    subject: str = "Ward update",
    date: datetime | None = datetime(2026, 9, 1, 8, 30),
) -> MailboxEmail:
    return MailboxEmail(uid=uid, sender=sender, subject=subject, date=date)


class TestFetchStoredEmailUids(unittest.TestCase):
    """Test paging through stored newsletter UIDs."""

    def setUp(self):
        self.mock_supabase = Mock()
        self.mock_table = Mock()
        self.mock_supabase.table.return_value = self.mock_table
        self.mock_table.select.return_value = self.mock_table
        self.mock_table.order.return_value = self.mock_table
        self.mock_table.range.return_value = self.mock_table

    def test_pages_until_short_page(self):
        """Fetches successive pages and stops after a page smaller than page_size."""
        self.mock_table.execute.side_effect = [
            Mock(data=[{"id": 1, "email_uid": "1"}, {"id": 2, "email_uid": "2"}]),
            Mock(data=[{"id": 3, "email_uid": "3"}]),
        ]

        result = fetch_stored_email_uids(self.mock_supabase, page_size=2)

        self.assertEqual(result, {"1", "2", "3"})
        self.mock_table.range.assert_any_call(0, 1)
        self.mock_table.range.assert_any_call(2, 3)
        self.assertEqual(self.mock_table.execute.call_count, 2)

    def test_orders_query_for_stable_pagination(self):
        """Orders by id so pages neither overlap nor skip rows."""
        self.mock_table.execute.return_value = Mock(data=[])

        fetch_stored_email_uids(self.mock_supabase)

        self.mock_table.order.assert_called_once_with("id")

    def test_skips_null_uids(self):
        """Scraped newsletters have no email_uid and are excluded."""
        self.mock_table.execute.return_value = Mock(
            data=[{"id": 1, "email_uid": "10"}, {"id": 2, "email_uid": None}]
        )

        result = fetch_stored_email_uids(self.mock_supabase)

        self.assertEqual(result, {"10"})

    def test_exact_multiple_of_page_size_fetches_empty_final_page(self):
        """A full last page triggers one more fetch, which returns empty."""
        self.mock_table.execute.side_effect = [
            Mock(data=[{"id": 1, "email_uid": "1"}, {"id": 2, "email_uid": "2"}]),
            Mock(data=[]),
        ]

        result = fetch_stored_email_uids(self.mock_supabase, page_size=2)

        self.assertEqual(result, {"1", "2"})
        self.assertEqual(self.mock_table.execute.call_count, 2)


class TestFetchMailboxEmails(unittest.TestCase):
    """Test that mailbox fetching is read-only and maps header fields."""

    def setUp(self):
        self.mock_mailbox = Mock()
        self.mock_mailbox.fetch.return_value = [
            Mock(
                uid="42",
                from_="ward@example.org",
                subject="Hello",
                date=datetime(2026, 9, 1),
            ),
            Mock(uid="43", from_="other@example.org", subject=None, date=None),
        ]

    def test_fetches_without_marking_seen(self):
        """Never marks messages read; doing so would hide them from ingestion."""
        fetch_mailbox_emails(self.mock_mailbox, "INBOX")

        self.mock_mailbox.fetch.assert_called_once_with(
            headers_only=True, mark_seen=False, bulk=True
        )

    def test_selects_requested_folder(self):
        fetch_mailbox_emails(self.mock_mailbox, "[Gmail]/Spam")

        self.mock_mailbox.folder.set.assert_called_once_with("[Gmail]/Spam")

    def test_maps_header_fields(self):
        result = fetch_mailbox_emails(self.mock_mailbox, "INBOX")

        self.assertEqual(
            result,
            [
                make_email("42", "ward@example.org", "Hello", datetime(2026, 9, 1)),
                make_email("43", "other@example.org", "", None),
            ],
        )


class TestFindUnprocessedEmails(unittest.TestCase):
    """Test diffing mailbox emails against stored UIDs."""

    def test_returns_only_unstored_emails(self):
        emails = [make_email("1"), make_email("2"), make_email("3")]

        result = find_unprocessed_emails(emails, {"1", "3"})

        self.assertEqual([email.uid for email in result], ["2"])

    def test_empty_stored_set_returns_all(self):
        emails = [make_email("1"), make_email("2")]

        result = find_unprocessed_emails(emails, set())

        self.assertEqual(len(result), 2)

    def test_sorts_by_sender_case_insensitively_then_date(self):
        emails = [
            make_email("1", "b@example.org", date=datetime(2026, 9, 2)),
            make_email("2", "A@example.org", date=datetime(2026, 9, 3)),
            make_email("3", "b@example.org", date=datetime(2026, 9, 1)),
            make_email("4", "b@example.org", date=None),
        ]

        result = find_unprocessed_emails(emails, set())

        self.assertEqual([email.uid for email in result], ["2", "4", "3", "1"])


class TestFormatTsvRow(unittest.TestCase):
    """Test TSV row formatting."""

    def test_formats_fields_in_order(self):
        email = make_email("42", "ward@example.org", "Hello", datetime(2026, 9, 1, 8))

        self.assertEqual(
            format_tsv_row(email),
            "2026-09-01T08:00:00\t42\tward@example.org\tHello",
        )

    def test_missing_date_is_unknown(self):
        row = format_tsv_row(make_email("42", date=None))

        self.assertTrue(row.startswith("unknown\t"))

    def test_escapes_tabs_and_newlines(self):
        email = make_email("42", subject="Line one\tcol\r\nLine two")

        fields = format_tsv_row(email).split("\t")

        self.assertEqual(len(fields), 4)
        self.assertNotIn("\n", fields[3])

    def test_truncates_long_subject(self):
        row = format_tsv_row(make_email("42", subject="x" * 200))

        self.assertEqual(len(row.split("\t")[3]), 70)


if __name__ == "__main__":
    unittest.main()
