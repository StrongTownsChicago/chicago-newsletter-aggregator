"""Process newsletters with LLM to add or update metadata (topics, summary).

Usage:
    # Process latest 10 newsletters
    uv run python -m cli.process_llm_metadata --latest 10

    # Skip first 20, process next 10 (newsletters 21-30)
    uv run python -m cli.process_llm_metadata --latest 10 --skip 20

    # Process all newsletters from source_id 5
    uv run python -m cli.process_llm_metadata --source-id 5

    # Process only newsletters missing LLM metadata
    uv run python -m cli.process_llm_metadata --missing-metadata

    # Process and queue notifications for matched rules
    uv run python -m cli.process_llm_metadata --latest 10 --queue-notifications

    # Combine filters: latest 20 from source 3
    uv run python -m cli.process_llm_metadata --latest 20 --source-id 3

    # Dry run (preview what would be processed)
    uv run python -m cli.process_llm_metadata --latest 10 --dry-run
"""

import argparse
import os
from typing import Any, cast

from dotenv import load_dotenv

from cli.logging_setup import configure_cli_logging
from processing.llm_processor import extract_newsletter_metadata
from shared.db import fetch_all_rows, get_supabase_client

load_dotenv()

# Runs larger than this ask for confirmation first.
LARGE_RUN_THRESHOLD = 100


def fetch_newsletters(supabase: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Fetch newsletters based on filter arguments, newest first."""

    def build_query() -> Any:
        # Join with sources table to get ward_number
        query = supabase.table("newsletters").select("*, sources(ward_number)")

        if args.newsletter_id:
            query = query.eq("id", args.newsletter_id)

        if args.source_id:
            query = query.eq("source_id", args.source_id)

        if args.missing_metadata:
            # Newsletters where ANY metadata is missing
            query = query.or_("topics.is.null,summary.is.null")

        # id breaks date ties, so pages never overlap
        return query.order("received_date", desc=True).order("id")

    if args.latest and not args.all:
        start = args.skip
        end = args.skip + args.latest - 1
        return cast(
            list[dict[str, Any]], build_query().range(start, end).execute().data
        )

    # Everything after skip, read in pages past the API's row cap
    return fetch_all_rows(build_query, start=args.skip)


def reprocess_newsletter(
    supabase: Any,
    newsletter: dict[str, Any],
    model: str,
    dry_run: bool = False,
    queue_notifications_flag: bool = False,
) -> bool:
    """Reprocess a single newsletter with LLM."""

    newsletter_id = newsletter["id"]
    subject = newsletter["subject"]

    print(f"\nProcessing: {subject}")
    print(f"  ID: {newsletter_id}")
    print(f"  Source ID: {newsletter['source_id']}")
    print(f"  Date: {newsletter['received_date']}")

    if dry_run:
        print("  [DRY RUN - Skipping LLM processing]")
        return True

    # Check if newsletter has content to process
    if not newsletter.get("plain_text"):
        print("  ⚠️  No plain_text content, skipping")
        return False

    try:
        # Run LLM processing
        llm_data = extract_newsletter_metadata(newsletter, model)

        # Update database
        update_result = (
            supabase.table("newsletters")
            .update(
                {
                    "topics": llm_data["topics"],
                    "summary": llm_data["summary"],
                }
            )
            .eq("id", newsletter_id)
            .execute()
        )

        if update_result.data:
            print("  ✓ Updated successfully")
            topics = llm_data["topics"]
            topics_str = (
                ", ".join(topics) if isinstance(topics, list) and topics else "none"
            )
            print(f"    Topics: {topics_str}")

            # Queue notifications if enabled
            if queue_notifications_flag:
                try:
                    from notifications.rule_matcher import (
                        match_newsletter_to_rules,
                    )
                    from notifications.rule_matcher import (
                        queue_notifications as queue_notifs,
                    )

                    # Prepare newsletter data for matching
                    newsletter_data = {
                        "topics": llm_data.get("topics", []),
                        "plain_text": newsletter.get("plain_text", ""),
                        "source_id": newsletter.get("source_id"),
                        "ward_number": newsletter.get("sources", {}).get("ward_number")
                        if newsletter.get("sources")
                        else None,
                    }

                    # Match and queue
                    matched = match_newsletter_to_rules(newsletter_id, newsletter_data)
                    if matched:
                        queued = queue_notifs(newsletter_id, matched)
                        print(f"    ✓ Queued {queued} notification(s)")
                    else:
                        print("    - No matching notification rules")

                except Exception as e:  # noqa: BLE001  notification queuing must not fail LLM processing
                    # Don't fail LLM processing if notification queuing fails
                    print(f"    ⚠️  Notification queuing failed: {e}")

            return True
        print("  ✗ Update failed")
        return False

    except Exception as e:  # noqa: BLE001  per-newsletter boundary: log and continue
        print(f"  ✗ Processing failed: {e}")
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reprocess existing newsletters with updated LLM processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Filter options
    parser.add_argument(
        "--latest", type=int, help="Process the N most recent newsletters"
    )

    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the first N newsletters (useful with --latest to process next batch)",
    )

    parser.add_argument(
        "--source-id", type=int, help="Only process newsletters from this source ID"
    )

    parser.add_argument(
        "--newsletter-id", type=str, help="Process a specific newsletter by ID"
    )

    parser.add_argument(
        "--missing-metadata",
        action="store_true",
        help="Only process newsletters that are missing LLM metadata (topics or summary)",
    )

    parser.add_argument(
        "--all", action="store_true", help="Process ALL newsletters (use with caution!)"
    )

    # Processing options
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "gpt-oss:20b")),
        help="LLM model to use, with optional provider prefix (e.g., openai:gpt-5, ollama:gpt-oss:20b). Default: from LLM_MODEL or OLLAMA_MODEL env var",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be processed without actually running LLM",
    )

    parser.add_argument(
        "--queue-notifications",
        action="store_true",
        help="Queue notifications for matched rules after processing (default: false)",
    )

    return parser


def parse_args() -> argparse.Namespace:
    """Parse the command line; exits with a usage error unless a filter is given."""
    parser = build_parser()
    args = parser.parse_args()

    if not any(
        [
            args.latest,
            args.source_id,
            args.newsletter_id,
            args.all,
            args.missing_metadata,
        ]
    ):
        parser.error(
            "Must specify at least one filter: --latest, --source-id, --newsletter-id, --all, or --missing-metadata"
        )

    if args.all and args.latest:
        parser.error("Cannot use --all with --latest (--all processes everything)")

    return args


def confirm_large_run(newsletter_count: int) -> bool:
    """Ask before processing more than LARGE_RUN_THRESHOLD newsletters."""
    if newsletter_count <= LARGE_RUN_THRESHOLD:
        return True
    confirm = input(
        f"\nAbout to process {newsletter_count} newsletters. Continue? (y/N): "
    )
    if confirm.lower() != "y":
        print("Cancelled")
        return False
    return True


def reprocess_newsletters(
    supabase: Any, newsletters: list[dict[str, Any]], args: argparse.Namespace
) -> tuple[int, int]:
    """Reprocess each newsletter until done or interrupted; returns (succeeded, failed)."""
    success_count = 0
    fail_count = 0

    for newsletter in newsletters:
        try:
            success = reprocess_newsletter(
                supabase,
                newsletter,
                args.model,
                args.dry_run,
                args.queue_notifications,
            )
            if success:
                success_count += 1
            else:
                fail_count += 1
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            break
        except Exception as e:  # noqa: BLE001  per-newsletter boundary: log and continue
            print(f"  ✗ Unexpected error: {e}")
            fail_count += 1

    return success_count, fail_count


def main() -> None:
    args = parse_args()

    enable_llm = os.getenv("ENABLE_LLM", "false").lower() == "true"
    if not enable_llm and not args.dry_run:
        print("⚠️  ENABLE_LLM is not set to 'true' in .env")
        print("Set ENABLE_LLM=true to enable LLM processing")
        return

    print("Connecting to database...")
    supabase = get_supabase_client()

    print("Fetching newsletters...")
    newsletters = fetch_newsletters(supabase, args)

    if not newsletters:
        print("No newsletters found matching criteria")
        return

    print(f"\nFound {len(newsletters)} newsletter(s) to process")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        print("The following newsletters would be processed:\n")
    elif not confirm_large_run(len(newsletters)):
        return

    success_count, fail_count = reprocess_newsletters(supabase, newsletters, args)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    if args.dry_run:
        print(f"Would process: {len(newsletters)} newsletter(s)")
    else:
        print(f"Processed: {success_count} successful, {fail_count} failed")


if __name__ == "__main__":
    configure_cli_logging()
    main()
