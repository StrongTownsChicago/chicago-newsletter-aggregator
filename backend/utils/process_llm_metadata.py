"""
Process newsletters with LLM to add or update metadata (topics, summary, relevance score).

Usage:
    # Process latest 10 newsletters
    uv run python -m utils.process_llm_metadata --latest 10

    # Skip first 20, process next 10 (newsletters 21-30)
    uv run python -m utils.process_llm_metadata --latest 10 --skip 20

    # Process all newsletters from source_id 5
    uv run python -m utils.process_llm_metadata --source-id 5

    # Process only newsletters missing LLM metadata
    uv run python -m utils.process_llm_metadata --missing-metadata

    # Process and queue notifications for matched rules
    uv run python -m utils.process_llm_metadata --latest 10 --queue-notifications

    # Process all newsletters
    uv run python -m utils.process_llm_metadata --all

    # Process specific newsletter by ID
    uv run python -m utils.process_llm_metadata --newsletter-id abc-123-def

    # Combine filters: latest 20 from source 3
    uv run python -m utils.process_llm_metadata --latest 20 --source-id 3

    # Dry run (preview what would be processed)
    uv run python -m utils.process_llm_metadata --latest 10 --dry-run
"""

import os
import argparse
from dotenv import load_dotenv
from shared.db import get_supabase_client
from processing.llm_processor import process_with_ollama

load_dotenv()


def fetch_newsletters(supabase, args):
    """Fetch newsletters based on filter arguments."""

    # Join with sources table to get ward_number
    query = supabase.table("newsletters").select("*, sources(ward_number)")

    # Apply filters
    if args.newsletter_id:
        query = query.eq("id", args.newsletter_id)

    if args.source_id:
        query = query.eq("source_id", args.source_id)

    # Filter for missing metadata
    if args.missing_metadata:
        # Filter for newsletters where ANY metadata is missing
        # Using OR logic: topics is null OR summary is null OR relevance_score is null
        query = query.or_("topics.is.null,summary.is.null,relevance_score.is.null")

    # Order by date for consistency
    query = query.order("received_date", desc=True)

    # Apply limit and skip using range
    if args.latest and not args.all:
        start = args.skip
        end = args.skip + args.latest - 1
        query = query.range(start, end)
    elif args.skip > 0:
        # If only skip is specified (no limit), skip and get everything after
        query = query.range(args.skip, args.skip + 999999)

    result = query.execute()
    return result.data


def reprocess_newsletter(
    supabase, newsletter, model, dry_run=False, queue_notifications_flag=False
):
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
        llm_data = process_with_ollama(newsletter, model)

        # Update database
        update_result = (
            supabase.table("newsletters")
            .update(
                {
                    "topics": llm_data["topics"],
                    "summary": llm_data["summary"],
                    "relevance_score": llm_data["relevance_score"],
                }
            )
            .eq("id", newsletter_id)
            .execute()
        )

        if update_result.data:
            print("  ✓ Updated successfully")
            print(
                f"    Topics: {', '.join(llm_data['topics']) if llm_data['topics'] else 'none'}"
            )
            print(f"    Score: {llm_data['relevance_score']}/10")

            # Queue notifications if enabled
            if queue_notifications_flag:
                try:
                    from notifications.rule_matcher import (
                        match_newsletter_to_rules,
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
                        "relevance_score": llm_data.get("relevance_score"),
                    }

                    # Match and queue
                    matched = match_newsletter_to_rules(newsletter_id, newsletter_data)
                    if matched:
                        queued = queue_notifs(newsletter_id, matched)
                        print(f"    ✓ Queued {queued} notification(s)")
                    else:
                        print("    - No matching notification rules")

                except Exception as e:
                    # Don't fail LLM processing if notification queuing fails
                    print(f"    ⚠️  Notification queuing failed: {e}")

            return True
        else:
            print("  ✗ Update failed")
            return False

    except Exception as e:
        print(f"  ✗ Processing failed: {e}")
        return False


def main():
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
        help="Only process newsletters that are missing LLM metadata (topics, summary, or relevance_score)",
    )

    parser.add_argument(
        "--all", action="store_true", help="Process ALL newsletters (use with caution!)"
    )

    # Processing options
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("OLLAMA_MODEL", "gpt-oss:20b"),
        help="Ollama model to use (default: from OLLAMA_MODEL env var)",
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

    args = parser.parse_args()

    # Validate arguments
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

    # Check if LLM is enabled
    enable_llm = os.getenv("ENABLE_LLM", "false").lower() == "true"
    if not enable_llm and not args.dry_run:
        print("⚠️  ENABLE_LLM is not set to 'true' in .env")
        print("Set ENABLE_LLM=true to enable LLM processing")
        return

    # Connect to database
    print("Connecting to database...")
    supabase = get_supabase_client()

    # Fetch newsletters
    print("Fetching newsletters...")
    newsletters = fetch_newsletters(supabase, args)

    if not newsletters:
        print("No newsletters found matching criteria")
        return

    print(f"\nFound {len(newsletters)} newsletter(s) to process")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        print("The following newsletters would be processed:\n")

    # Confirm if processing many newsletters
    if len(newsletters) > 10 and not args.dry_run:
        confirm = input(
            f"\nAbout to process {len(newsletters)} newsletters. Continue? (y/N): "
        )
        if confirm.lower() != "y":
            print("Cancelled")
            return

    # Process newsletters
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
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            fail_count += 1

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    if args.dry_run:
        print(f"Would process: {len(newsletters)} newsletter(s)")
    else:
        print(f"Processed: {success_count} successful, {fail_count} failed")


if __name__ == "__main__":
    main()
