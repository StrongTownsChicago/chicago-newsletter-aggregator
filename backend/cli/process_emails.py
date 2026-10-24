"""
Gmail IMAP Email Ingestion

Processes unread newsletters from Gmail inbox, matches them to sources, and stores in database.

Usage:
    Run from the backend/ directory:

    $ uv run python -m cli.process_emails

Required environment variables (.env file):
    - GMAIL_ADDRESS: Gmail account email address
    - GMAIL_APP_PASSWORD: Gmail app-specific password (not regular password)
    - SUPABASE_URL: Supabase project URL
    - SUPABASE_SERVICE_KEY: Supabase service role key

Optional environment variables:
    - ENABLE_LLM=true: Process newsletters with Ollama for topic extraction (default: false)
    - ENABLE_NOTIFICATIONS=true: Queue notifications for matched rules (default: false)
    - OLLAMA_MODEL: LLM model name (default: gpt-oss:20b)

Output:
    - Processes unread emails and marks them as read
    - Generates unmapped_emails_TIMESTAMP.txt report if any emails couldn't be matched to sources
    - Prints summary of processed/skipped/unmapped counts
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from imap_tools import AND, MailBox, MailMessageFlags  # type: ignore[attr-defined]

from cli.ingest_summary import print_summary
from cli.logging_setup import configure_cli_logging
from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import parse_newsletter
from shared.dates import CHICAGO_TIMEZONE
from shared.db import get_supabase_client

load_dotenv()

# Configuration
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "false").lower() == "true"

supabase = get_supabase_client()


def newsletter_exists(email_uid: str) -> bool:
    """Check if newsletter already processed"""
    result = (
        supabase.table("newsletters").select("id").eq("email_uid", email_uid).execute()
    )
    return len(result.data) > 0


def save_unmapped_report(unmapped_emails: list[dict[str, str]]) -> None:
    """Save unmapped emails to a log file"""
    if not unmapped_emails:
        return

    timestamp = datetime.now(CHICAGO_TIMEZONE).strftime("%Y%m%d_%H%M%S")
    filename = f"unmapped_emails_{timestamp}.txt"

    with Path(filename).open("w", encoding="utf-8") as f:
        f.write(f"Unmapped Emails Report - {datetime.now(CHICAGO_TIMEZONE)}\n")
        f.write("=" * 60 + "\n\n")

        for i, email in enumerate(unmapped_emails, 1):
            f.write(f"{i}. From: {email['from']}\n")
            f.write(f"   Subject: {email['subject']}\n")
            f.write(f"   Date: {email['date']}\n\n")

    print(f"\n  Report saved to: {filename}")


def process_new_newsletters() -> None:
    """
    Ingest unread Gmail newsletters: match sources, optionally run the LLM, store.

    Only unread emails are fetched, and ones already stored (by email_uid) are
    skipped. Every email is marked read after processing, including unmapped ones,
    which are logged to a timestamped report file. A failing email does not stop
    the run. Environment variables are listed in the module docstring.
    """

    print(f"[{datetime.now(CHICAGO_TIMEZONE)}] Starting newsletter ingestion...")

    # Validate credentials
    if not GMAIL_ADDRESS or not GMAIL_PASSWORD:
        raise ValueError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set")

    # Connect to Gmail
    with MailBox("imap.gmail.com").login(GMAIL_ADDRESS, GMAIL_PASSWORD) as mailbox:  # type: ignore[no-untyped-call]
        # Fetch unread emails
        messages = mailbox.fetch(AND(seen=False))
        # To process every email when testing, call mailbox.fetch() with no criteria.

        processed_count = 0
        skipped_count = 0
        unmapped_count = 0
        unmapped_emails = []  # Track unmapped emails for summary

        for msg in messages:
            try:
                # Skip if already processed
                if newsletter_exists(msg.uid):
                    print(f"⊘ Duplicate: {msg.subject[:50]}...")
                    skipped_count += 1
                    continue

                # Parse email
                print(f"Processing: {msg.subject}")
                newsletter = parse_newsletter(msg, supabase, PRIVACY_PATTERNS_DICT)

                # Check if source was matched
                if newsletter["source_id"] is None:
                    unmapped_count += 1
                    unmapped_info = {
                        "from": msg.from_,
                        "subject": msg.subject,
                        "date": msg.date.isoformat() if msg.date else "Unknown",
                    }
                    unmapped_emails.append(unmapped_info)

                    print(f"✗ Unmapped: {msg.subject[:50]}... (from: {msg.from_})")

                    # Mark as read anyway so we don't keep processing it
                    mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)
                    continue

                # Optional: Process with LLM if enabled
                if ENABLE_LLM:
                    try:
                        from processing.llm_processor import extract_newsletter_metadata

                        llm_model = os.getenv(
                            "LLM_MODEL", os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
                        )
                        llm_result = extract_newsletter_metadata(newsletter, llm_model)
                        newsletter.update(llm_result)
                        print("  LLM processing complete")
                    except ImportError:
                        print("  Warning: LLM enabled but llm_processor not found")
                    except Exception as e:  # noqa: BLE001  optional LLM step must not fail ingestion
                        print(f"  Warning: LLM processing failed: {e}")

                # Extract ward_number for notifications, but remove from dict for DB insertion
                ward_number = newsletter.pop("ward_number", None)

                # Insert into Supabase
                insert_response = (
                    supabase.table("newsletters").insert(newsletter).execute()
                )

                # Queue notifications for matched rules
                if (
                    ENABLE_NOTIFICATIONS
                    and insert_response.data
                    and len(insert_response.data) > 0
                ):
                    response_data = cast(list[dict[str, Any]], insert_response.data)
                    newsletter_id = cast(str, response_data[0]["id"])

                    try:
                        from notifications.rule_matcher import (
                            match_newsletter_to_rules,
                            queue_notifications,
                        )

                        # Prepare newsletter data for matching
                        newsletter_data = {
                            "topics": newsletter.get("topics", []),
                            "plain_text": newsletter.get("plain_text", ""),
                            "source_id": newsletter.get("source_id"),
                            "ward_number": ward_number,
                        }

                        # Match and queue
                        matched = match_newsletter_to_rules(
                            newsletter_id, newsletter_data
                        )
                        if matched:
                            queued = queue_notifications(newsletter_id, matched)
                            print(f"  ✓ Queued {queued} notification(s)")
                    except Exception as e:  # noqa: BLE001  notification queuing must not fail ingestion
                        # Don't fail newsletter ingestion if notification queuing fails
                        print(f"  ⚠️  Notification queuing failed: {e}")

                # Mark as read
                mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)

                processed_count += 1
                print("  ✓ Stored in database")

            except Exception as e:  # noqa: BLE001  per-email boundary: log and continue
                print(f"✗ Error processing {msg.uid}: {e}")
                continue

        if unmapped_emails:
            save_unmapped_report(unmapped_emails)

        print_summary(processed_count, skipped_count, unmapped_count)


if __name__ == "__main__":
    configure_cli_logging()
    process_new_newsletters()
