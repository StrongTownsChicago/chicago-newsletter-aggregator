"""
Unit tests for replay_unprocessed_emails utility.

Tests candidate selection and filtering, grouping/report formatting, and that the
only mailbox mutation is clearing \\Seen on selected UIDs, and only with --apply.
"""

import io
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from imap_tools import MailMessageFlags  # type: ignore[attr-defined]

from utils.find_unprocessed_emails import MailboxEmail
from utils.replay_unprocessed_emails import (
    ReplayCandidate,
    ReplayFilters,
    find_unmatched_requested_uids,
    format_follow_up_commands,
    format_replay_report,
    format_selection_summary,
    group_candidates_by_source,
    main,
    mark_candidates_unread,
    resolve_sender_sources,
    select_replay_candidates,
)

WARD_28 = {"id": 28, "name": "Jason Ervin"}
WARD_21 = {"id": 21, "name": "Ronnie Mosley"}


def make_email(
    uid: str,
    sender: str = "jason@aldermanervin.com",
    subject: str = "Ward update",
    date: datetime | None = datetime(2026, 9, 1, 8, 30),
) -> MailboxEmail:
    return MailboxEmail(uid=uid, sender=sender, subject=subject, date=date)


def make_candidate(uid: str, source: dict[str, Any] = WARD_28) -> ReplayCandidate:
    return ReplayCandidate(
        email=make_email(uid), source_id=source["id"], source_name=source["name"]
    )


SENDER_SOURCES: dict[str, dict[str, Any] | None] = {
    "jason@aldermanervin.com": WARD_28,
    "info@ronniemosley.com": WARD_21,
    "unknown@example.org": None,
}


class TestResolveSenderSources(unittest.TestCase):
    """Test that each distinct sender is resolved exactly once."""

    @patch("utils.replay_unprocessed_emails.lookup_source_by_email")
    def test_looks_up_each_sender_once(self, mock_lookup):
        mock_lookup.side_effect = lambda sender, _: (
            WARD_28 if sender.endswith("aldermanervin.com") else None
        )
        supabase = Mock()

        result = resolve_sender_sources(
            {"jason@aldermanervin.com", "unknown@example.org"}, supabase
        )

        self.assertEqual(
            result,
            {"jason@aldermanervin.com": WARD_28, "unknown@example.org": None},
        )
        self.assertEqual(mock_lookup.call_count, 2)
        mock_lookup.assert_any_call("jason@aldermanervin.com", supabase)


class TestSelectReplayCandidates(unittest.TestCase):
    """Test selection of unprocessed emails from mapped senders."""

    def setUp(self):
        self.unprocessed = [
            make_email("1", "jason@aldermanervin.com", date=datetime(2026, 8, 15)),
            make_email("2", "info@ronniemosley.com", date=datetime(2026, 9, 10)),
            make_email("3", "unknown@example.org", date=datetime(2026, 9, 12)),
            make_email("4", "jason@aldermanervin.com", date=None),
        ]

    def select_uids(self, filters: ReplayFilters) -> list[str]:
        candidates = select_replay_candidates(self.unprocessed, SENDER_SOURCES, filters)
        return [candidate.email.uid for candidate in candidates]

    def test_excludes_unmapped_senders(self):
        self.assertEqual(self.select_uids(ReplayFilters()), ["1", "2", "4"])

    def test_sender_missing_from_lookup_is_excluded(self):
        candidates = select_replay_candidates(
            [make_email("9", "new@example.org")], SENDER_SOURCES, ReplayFilters()
        )

        self.assertEqual(candidates, [])

    def test_attaches_source_id_and_name(self):
        candidates = select_replay_candidates(
            self.unprocessed[:1], SENDER_SOURCES, ReplayFilters()
        )

        self.assertEqual(candidates[0].source_id, 28)
        self.assertEqual(candidates[0].source_name, "Jason Ervin")

    def test_filters_by_source_id(self):
        self.assertEqual(self.select_uids(ReplayFilters(source_id=21)), ["2"])

    def test_filters_by_uids(self):
        filters = ReplayFilters(uids=frozenset({"1", "3"}))

        # UID 3 is requested but unmapped, so it is still excluded
        self.assertEqual(self.select_uids(filters), ["1"])

    def test_since_is_inclusive_and_excludes_undated(self):
        filters = ReplayFilters(since=date(2026, 9, 10))

        self.assertEqual(self.select_uids(filters), ["2"])

    def test_filters_combine_with_and(self):
        filters = ReplayFilters(
            uids=frozenset({"1", "2"}), source_id=28, since=date(2026, 8, 1)
        )

        self.assertEqual(self.select_uids(filters), ["1"])


class TestGroupingAndFormatting(unittest.TestCase):
    """Test grouping by source and report rendering."""

    def test_groups_largest_first(self):
        candidates = [
            make_candidate("1", WARD_21),
            make_candidate("2", WARD_28),
            make_candidate("3", WARD_28),
        ]

        groups = group_candidates_by_source(candidates)

        self.assertEqual(list(groups), [(28, "Jason Ervin"), (21, "Ronnie Mosley")])
        self.assertEqual(len(groups[(28, "Jason Ervin")]), 2)

    def test_report_has_header_with_count_and_email_lines(self):
        report = format_replay_report([make_candidate("7"), make_candidate("8")])

        lines = report.splitlines()
        self.assertEqual(lines[0], "[28] Jason Ervin: 2")
        self.assertIn("uid=7", lines[1])
        self.assertIn("2026-09-01", lines[1])

    def test_summary_counts_unmapped_and_selected(self):
        unprocessed = [
            make_email("1"),
            make_email("2", "unknown@example.org"),
        ]
        candidates = [make_candidate("1")]

        summary = format_selection_summary(
            10, unprocessed, SENDER_SOURCES, candidates, ReplayFilters()
        )

        self.assertIn("2 of 10 INBOX messages", summary)
        self.assertIn("1 are from still-unmapped senders", summary)
        self.assertIn("Selected 1 email(s) from 1 source(s)", summary)

    def test_summary_reports_nothing_to_replay(self):
        summary = format_selection_summary(0, [], {}, [], ReplayFilters())

        self.assertIn("Nothing to replay.", summary)

    def test_unmatched_requested_uids_sorted_numerically(self):
        unmatched = find_unmatched_requested_uids(
            frozenset({"100", "9", "5"}), [make_candidate("5")]
        )

        self.assertEqual(unmatched, ["9", "100"])

    def test_no_requested_uids_means_no_unmatched(self):
        self.assertEqual(find_unmatched_requested_uids(None, []), [])

    def test_follow_up_includes_ingestion_and_llm_backfill(self):
        commands = format_follow_up_commands(42)

        self.assertIn("uv run python -m ingest.email.process_emails", commands)
        self.assertIn("--missing-metadata --latest 42", commands)


class TestMarkCandidatesUnread(unittest.TestCase):
    """Test the single mailbox mutation."""

    def test_clears_seen_for_candidate_uids(self):
        mailbox = Mock()

        mark_candidates_unread(mailbox, [make_candidate("1"), make_candidate("2")])

        mailbox.flag.assert_called_once_with(["1", "2"], MailMessageFlags.SEEN, False)

    def test_no_candidates_makes_no_call(self):
        mailbox = Mock()

        mark_candidates_unread(mailbox, [])

        mailbox.flag.assert_not_called()


class TestMain(unittest.TestCase):
    """Test end-to-end wiring: dry run never mutates, --apply flags only selected."""

    def setUp(self):
        self.mailbox = MagicMock()
        self.mailbox.fetch.return_value = [
            Mock(
                uid="1",
                from_="jason@aldermanervin.com",
                subject="A",
                date=datetime(2026, 9, 1),
            ),
            Mock(
                uid="2",
                from_="unknown@example.org",
                subject="B",
                date=datetime(2026, 9, 2),
            ),
            Mock(
                uid="3",
                from_="info@ronniemosley.com",
                subject="C",
                date=datetime(2026, 9, 3),
            ),
            Mock(
                uid="4",
                from_="jason@aldermanervin.com",
                subject="Stored",
                date=datetime(2026, 9, 4),
            ),
        ]
        mailbox_factory = MagicMock()
        mailbox_factory.return_value.login.return_value.__enter__.return_value = (
            self.mailbox
        )

        patchers = [
            patch("utils.replay_unprocessed_emails.MailBox", mailbox_factory),
            patch("utils.replay_unprocessed_emails.load_dotenv"),
            patch("utils.replay_unprocessed_emails.get_supabase_client"),
            patch(
                "utils.replay_unprocessed_emails.fetch_stored_email_uids",
                return_value={"4"},
            ),
            patch(
                "utils.replay_unprocessed_emails.lookup_source_by_email",
                side_effect=lambda sender, _: SENDER_SOURCES.get(sender),
            ),
            patch.dict(
                "os.environ",
                {"GMAIL_ADDRESS": "test@example.org", "GMAIL_APP_PASSWORD": "pw"},
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> str:
        output = io.StringIO()
        with (
            patch("sys.argv", ["replay_unprocessed_emails", *argv]),
            redirect_stdout(output),
        ):
            main()
        return output.getvalue()

    def test_dry_run_makes_no_mailbox_mutation(self):
        output = self.run_main()

        self.mailbox.flag.assert_not_called()
        self.mailbox.delete.assert_not_called()
        self.mailbox.move.assert_not_called()
        self.assertIn("DRY RUN", output)
        self.assertIn("Selected 2 email(s) from 2 source(s)", output)

    def test_fetch_is_read_only(self):
        self.run_main()

        self.mailbox.fetch.assert_called_once_with(
            headers_only=True, mark_seen=False, bulk=True
        )

    def test_apply_clears_seen_only_for_selected_uids(self):
        output = self.run_main("--apply")

        self.mailbox.flag.assert_called_once()
        flagged_uids, flag, value = self.mailbox.flag.call_args.args
        self.assertEqual(sorted(flagged_uids), ["1", "3"])
        self.assertEqual(flag, MailMessageFlags.SEEN)
        self.assertFalse(value)
        self.mailbox.delete.assert_not_called()
        self.mailbox.move.assert_not_called()
        self.assertIn("Marked 2 email(s) unread.", output)
        self.assertIn("--missing-metadata --latest 2", output)

    def test_apply_respects_source_filter(self):
        self.run_main("--apply", "--source-id", "21")

        self.mailbox.flag.assert_called_once_with(["3"], MailMessageFlags.SEEN, False)

    def test_apply_with_no_candidates_makes_no_call(self):
        output = self.run_main("--apply", "--uids", "2", "4")

        self.mailbox.flag.assert_not_called()
        self.assertIn("Nothing to replay.", output)
        self.assertIn("Requested UIDs not selected", output)


if __name__ == "__main__":
    unittest.main()
