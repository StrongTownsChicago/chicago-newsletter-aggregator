"""
Replay Unprocessed Emails

Marks unprocessed Gmail messages unread so the next ingestion run stores them.
Ingestion fetches only unread mail and marks unmapped senders' mail read, so
emails that arrived before their sender was added to email_source_mappings are
never revisited. This utility finds INBOX messages with no newsletters row whose
sender now maps to a source, and clears their \\Seen flag.

Usage:
    Run from the backend/ directory:

    # Dry run (default): list what would be replayed, grouped by source
    $ uv run python -m utils.replay_unprocessed_emails

    # Limit to one source, or to mail received on or after a date
    $ uv run python -m utils.replay_unprocessed_emails --source-id 28
    $ uv run python -m utils.replay_unprocessed_emails --since 2026-09-01

    # Replay specific UIDs only
    $ uv run python -m utils.replay_unprocessed_emails --uids 1201 1202 1305

    # Mark the selected messages unread so ingestion picks them up
    $ uv run python -m utils.replay_unprocessed_emails --apply

Follow-up after --apply:
    $ uv run python -m ingest.email.process_emails
    $ uv run python -m utils.process_llm_metadata --missing-metadata

    No --latest limit: replayed emails keep their original received_date, so
    newer newsletters missing metadata would sort ahead of them and crowd them out.

Notes:
    - The only mailbox change ever made is clearing \\Seen on selected UIDs, and
      only with --apply. Nothing is marked read, moved, or deleted.
    - Messages whose sender is still unmapped are never selected; ingestion
      would just skip them again.
    - Whichever ingestion run stores replayed emails queues notifications if
      ENABLE_NOTIFICATIONS=true (as in the scheduled GitHub Actions workflow),
      so matching rules will alert users about these older newsletters.

Required environment variables (.env file):
    - GMAIL_ADDRESS, GMAIL_APP_PASSWORD
    - SUPABASE_URL, SUPABASE_SERVICE_KEY
"""

import argparse
import io
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from dotenv import load_dotenv
from imap_tools import MailBox, MailMessageFlags  # type: ignore[attr-defined]

from ingest.email.email_parser import lookup_source_by_email
from shared.db import get_supabase_client
from utils.find_unprocessed_emails import (
    INGESTED_FOLDER,
    MailboxEmail,
    fetch_mailbox_emails,
    fetch_stored_email_uids,
    find_unprocessed_emails,
)

SUBJECT_PREVIEW_LENGTH = 60


@dataclass(frozen=True)
class ReplayCandidate:
    """An unprocessed email whose sender now maps to a source."""

    email: MailboxEmail
    source_id: int
    source_name: str


@dataclass(frozen=True)
class ReplayFilters:
    """Optional user-supplied restrictions on which candidates are replayed."""

    uids: frozenset[str] | None = None
    source_id: int | None = None
    since: date | None = None


def resolve_sender_sources(
    senders: set[str], supabase: Any
) -> dict[str, dict[str, Any] | None]:
    """Look up the mapped source for each distinct sender (None when unmapped)."""
    return {sender: lookup_source_by_email(sender, supabase) for sender in senders}


def _passes_filters(
    email: MailboxEmail, source_id: int, filters: ReplayFilters
) -> bool:
    if filters.uids is not None and email.uid not in filters.uids:
        return False
    if filters.source_id is not None and source_id != filters.source_id:
        return False
    if filters.since is not None:
        return email.date is not None and email.date.date() >= filters.since
    return True


def select_replay_candidates(
    unprocessed: list[MailboxEmail],
    sender_sources: dict[str, dict[str, Any] | None],
    filters: ReplayFilters,
) -> list[ReplayCandidate]:
    """Keep unprocessed emails from mapped senders that pass every filter."""
    candidates = []
    for email in unprocessed:
        source = sender_sources.get(email.sender)
        if source is None or not _passes_filters(email, source["id"], filters):
            continue
        candidates.append(
            ReplayCandidate(
                email=email, source_id=source["id"], source_name=source["name"]
            )
        )
    return candidates


def group_candidates_by_source(
    candidates: list[ReplayCandidate],
) -> dict[tuple[int, str], list[ReplayCandidate]]:
    """Group candidates by (source_id, source_name), largest group first."""
    groups: dict[tuple[int, str], list[ReplayCandidate]] = defaultdict(list)
    for candidate in candidates:
        groups[(candidate.source_id, candidate.source_name)].append(candidate)
    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0][0])))


def format_replay_report(candidates: list[ReplayCandidate]) -> str:
    """Render candidates grouped by source with counts and per-email lines."""
    lines = []
    for (source_id, source_name), group in group_candidates_by_source(
        candidates
    ).items():
        lines.append(f"[{source_id}] {source_name}: {len(group)}")
        for candidate in group:
            email = candidate.email
            received = email.date.date().isoformat() if email.date else "unknown"
            subject = email.subject[:SUBJECT_PREVIEW_LENGTH]
            lines.append(f"    {received}  uid={email.uid}  {email.sender}  {subject}")
    return "\n".join(lines)


def find_unmatched_requested_uids(
    requested_uids: frozenset[str] | None, candidates: list[ReplayCandidate]
) -> list[str]:
    """Return requested UIDs that were not selected (stored, unmapped, or absent)."""
    if requested_uids is None:
        return []
    selected = {candidate.email.uid for candidate in candidates}
    # Numeric order for digit-only UIDs without failing on malformed input
    return sorted(requested_uids - selected, key=lambda uid: (len(uid), uid))


def format_selection_summary(
    mailbox_count: int,
    unprocessed: list[MailboxEmail],
    sender_sources: dict[str, dict[str, Any] | None],
    candidates: list[ReplayCandidate],
    filters: ReplayFilters,
) -> str:
    """Render the per-source report plus totals explaining what was selected."""
    unmapped_count = sum(
        1 for email in unprocessed if sender_sources.get(email.sender) is None
    )
    source_count = len(group_candidates_by_source(candidates))
    lines = [format_replay_report(candidates), ""] if candidates else []
    lines.append(
        f"{len(unprocessed)} of {mailbox_count} {INGESTED_FOLDER} messages have no "
        f"newsletters row; {unmapped_count} are from still-unmapped senders."
    )
    unmatched_uids = find_unmatched_requested_uids(filters.uids, candidates)
    if unmatched_uids:
        lines.append(
            "Requested UIDs not selected (stored, unmapped, filtered, or absent): "
            + ", ".join(unmatched_uids)
        )
    lines.append(
        f"Selected {len(candidates)} email(s) from {source_count} source(s) for replay."
        if candidates
        else "Nothing to replay."
    )
    return "\n".join(lines)


def mark_candidates_unread(mailbox: Any, candidates: list[ReplayCandidate]) -> None:
    """Clear \\Seen on the candidates' UIDs; the only mailbox mutation this tool makes."""
    if not candidates:
        return
    mailbox.flag(
        [candidate.email.uid for candidate in candidates], MailMessageFlags.SEEN, False
    )


def format_follow_up_commands() -> str:
    """Commands to ingest the replayed emails and backfill their LLM metadata."""
    return (
        "Next steps (from backend/):\n"
        "    uv run python -m ingest.email.process_emails\n"
        "    uv run python -m utils.process_llm_metadata --missing-metadata\n"
        "Note: an ingestion run with ENABLE_NOTIFICATIONS=true (including the "
        "scheduled GitHub Actions workflow) queues digest notifications for "
        "replayed emails that match user rules."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mark unprocessed INBOX emails from now-mapped senders unread so the "
            "next ingestion run stores them. Dry run unless --apply is given."
        )
    )
    parser.add_argument(
        "--uids", nargs="+", metavar="UID", help="Only replay these IMAP UIDs"
    )
    parser.add_argument(
        "--source-id", type=int, help="Only replay emails mapped to this source"
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Only replay emails received on or after this date",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Clear the \\Seen flag on selected emails (default: dry run)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    filters = ReplayFilters(
        uids=frozenset(args.uids) if args.uids else None,
        source_id=args.source_id,
        since=args.since,
    )

    load_dotenv()
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    if not gmail_address or not gmail_password:
        sys.exit("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set")

    # Subjects often contain emoji; Windows consoles default to a legacy codepage
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    supabase = get_supabase_client()
    stored_uids = fetch_stored_email_uids(supabase)

    with MailBox("imap.gmail.com").login(gmail_address, gmail_password) as mailbox:  # type: ignore[no-untyped-call]
        mailbox_emails = fetch_mailbox_emails(mailbox, INGESTED_FOLDER)
        unprocessed = find_unprocessed_emails(mailbox_emails, stored_uids)
        sender_sources = resolve_sender_sources(
            {email.sender for email in unprocessed}, supabase
        )
        candidates = select_replay_candidates(unprocessed, sender_sources, filters)

        print(
            format_selection_summary(
                len(mailbox_emails), unprocessed, sender_sources, candidates, filters
            )
        )
        if not candidates:
            return

        if args.apply:
            mark_candidates_unread(mailbox, candidates)
            print(f"Marked {len(candidates)} email(s) unread.")
        else:
            print("DRY RUN: nothing was changed. Re-run with --apply to replay.")

    print(format_follow_up_commands())


if __name__ == "__main__":
    main()
