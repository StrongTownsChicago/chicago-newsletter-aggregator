"""
Find Unprocessed Emails

Read-only audit that lists Gmail messages with no corresponding row in the
newsletters table. Use it to recover emails that ingestion dropped (errored
mid-processing) or never stored (unmapped senders).

Usage:
    Run from the backend/ directory:

    $ uv run python -m utils.find_unprocessed_emails > unprocessed.tsv
    $ uv run python -m utils.find_unprocessed_emails --folder "[Gmail]/Spam"

Output:
    UTF-8 tab-separated rows (date, uid, sender, subject) on stdout, sorted by sender
    so unmapped senders group together. A summary line is printed to stderr.

Notes:
    - Messages are fetched headers-only with mark_seen=False, so running this
      never changes read state in the mailbox.
    - IMAP UIDs are only unique within a folder. Ingestion reads INBOX, so
      stored UIDs are compared only against INBOX. For any other folder every
      message is reported, since nothing outside INBOX is ever ingested.

Required environment variables (.env file):
    - GMAIL_ADDRESS, GMAIL_APP_PASSWORD
    - SUPABASE_URL, SUPABASE_SERVICE_KEY
"""

import argparse
import io
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from imap_tools import MailBox  # type: ignore[attr-defined]

from shared.db import get_supabase_client

INGESTED_FOLDER = "INBOX"
SUPABASE_PAGE_SIZE = 1000
SUBJECT_MAX_LENGTH = 70


@dataclass(frozen=True)
class MailboxEmail:
    """Header fields of a mailbox message needed for the audit."""

    uid: str
    sender: str
    subject: str
    date: datetime | None


def fetch_stored_email_uids(
    supabase: Any, page_size: int = SUPABASE_PAGE_SIZE
) -> set[str]:
    """Fetch every non-null email_uid from newsletters, paging past the row cap."""
    stored_uids: set[str] = set()
    page_start = 0
    while True:
        result = (
            supabase.table("newsletters")
            .select("id, email_uid")
            .order("id")
            .range(page_start, page_start + page_size - 1)
            .execute()
        )
        rows = result.data or []
        stored_uids.update(row["email_uid"] for row in rows if row["email_uid"])
        if len(rows) < page_size:
            return stored_uids
        page_start += page_size


def fetch_mailbox_emails(mailbox: Any, folder: str) -> list[MailboxEmail]:
    """Fetch headers for every message in a folder without marking them read."""
    mailbox.folder.set(folder)
    return [
        MailboxEmail(
            uid=msg.uid,
            sender=msg.from_,
            subject=msg.subject or "",
            date=msg.date,
        )
        for msg in mailbox.fetch(headers_only=True, mark_seen=False, bulk=True)
    ]


def find_unprocessed_emails(
    mailbox_emails: list[MailboxEmail], stored_uids: set[str]
) -> list[MailboxEmail]:
    """Return emails whose UID is not stored, sorted by sender then date."""
    unprocessed = [email for email in mailbox_emails if email.uid not in stored_uids]
    return sorted(
        unprocessed,
        key=lambda email: (email.sender.lower(), email.date or datetime.min),
    )


def _clean_tsv_field(value: str) -> str:
    """Replace characters that would break a TSV row."""
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def format_tsv_row(email: MailboxEmail) -> str:
    """Format an email as a date/uid/sender/subject TSV row."""
    date = email.date.isoformat() if email.date else "unknown"
    fields = [date, email.uid, email.sender, email.subject[:SUBJECT_MAX_LENGTH]]
    return "\t".join(_clean_tsv_field(field) for field in fields)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List Gmail messages that have no row in the newsletters table."
    )
    parser.add_argument(
        "--folder",
        default=INGESTED_FOLDER,
        help=f"Mailbox folder to audit (default: {INGESTED_FOLDER})",
    )
    args = parser.parse_args()

    load_dotenv()
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    if not gmail_address or not gmail_password:
        sys.exit("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set")

    stored_uids = (
        fetch_stored_email_uids(get_supabase_client())
        if args.folder == INGESTED_FOLDER
        else set()
    )

    with MailBox("imap.gmail.com").login(gmail_address, gmail_password) as mailbox:  # type: ignore[no-untyped-call]
        mailbox_emails = fetch_mailbox_emails(mailbox, args.folder)

    unprocessed = find_unprocessed_emails(mailbox_emails, stored_uids)
    # Subjects often contain emoji; Windows redirects default to a legacy codepage
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    for email in unprocessed:
        print(format_tsv_row(email))

    print(
        f"{len(unprocessed)} of {len(mailbox_emails)} messages in {args.folder} "
        f"have no newsletters row ({len(stored_uids)} UIDs stored)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
