"""
Scrape newsletters from alderman websites and save to database.
"""

import os
import time
import random
from datetime import datetime
from typing import Any, cast
from dotenv import load_dotenv
from ingest.scraper.newsletter_scraper import NewsletterScraper
from shared.db import get_supabase_client
from shared.utils import parse_date_string, print_summary

load_dotenv()

# Configuration
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")

# Initialize clients
supabase = get_supabase_client()
scraper = NewsletterScraper()


def newsletter_exists(source_id: int, subject: str) -> bool:
    """Check if newsletter already processed"""
    result = (
        supabase.table("newsletters")
        .select("id")
        .eq("source_id", source_id)
        .eq("subject", subject)
        .execute()
    )
    return len(result.data) > 0


def get_source_archive_url(source_id: int) -> tuple[str, str]:
    """Fetch source info and archive URL from database"""
    result = (
        supabase.table("sources")
        .select("name, newsletter_archive_url")
        .eq("id", source_id)
        .execute()
    )

    if not result.data:
        raise ValueError(f"Source ID {source_id} not found in database")

    source = cast(dict[str, Any], result.data[0])

    if not source.get("newsletter_archive_url"):
        raise ValueError(
            f"Source '{source['name']}' (ID: {source_id}) has no newsletter_archive_url configured"
        )

    return cast(str, source["name"]), cast(str, source["newsletter_archive_url"])


def process_scraped_newsletters(source_id: int, limit: int | None = None) -> None:
    """Scrape and process newsletters for a specific source"""

    # Fetch archive URL from database
    source_name, archive_url = get_source_archive_url(source_id)

    print(f"\n{'=' * 60}")
    print(f"[{datetime.now()}] Scraping newsletters for source ID: {source_id}")
    print(f"Source: {source_name}")
    print(f"Archive URL: {archive_url}")
    print(f"{'=' * 60}\n")

    # Get list of newsletter links
    newsletter_links = scraper.extract_newsletter_links(archive_url)

    if limit:
        newsletter_links = newsletter_links[:limit]

    total = len(newsletter_links)
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    # Process each newsletter: fetch content + process
    for i, link_info in enumerate(newsletter_links, 1):
        print(f"\n[{i}/{total}] {link_info['date_str']} - {link_info['title'][:60]}")
        print(f"  URL: {link_info['url']}")

        try:
            # Fetch content
            content = scraper.fetch_newsletter_content(
                link_info["url"], link_info["title"], link_info["date_str"]
            )

            if not content:
                print("  ✗ Failed to fetch content")
                failed_count += 1
                continue

            print(f"  ✓ Retrieved {len(content['plain_text'])} chars")

            # Skip if duplicate
            if newsletter_exists(source_id, content["subject"]):
                print("  ⊘ Duplicate")
                skipped_count += 1
                # Add delay to avoid overly aggressive scraping if we are seeing many duplicates
                delay = random.uniform(1.0, 7.0)
                time.sleep(delay)
                continue

            # Build newsletter record
            received_date = parse_date_string(content.get("archive_date_str", ""))
            newsletter_data: dict[str, Any] = {
                "source_id": source_id,
                "received_date": received_date or datetime.now().isoformat(),
                "subject": content["subject"],
                "from_email": None,
                "to_email": None,
                "email_uid": None,
                "raw_html": content["html_content"],
                "plain_text": content["plain_text"],
            }

            # LLM processing or delay
            if ENABLE_LLM:
                try:
                    from processing.llm_processor import process_with_ollama

                    print("  LLM processing...")
                    llm_result = process_with_ollama(newsletter_data, OLLAMA_MODEL)
                    newsletter_data.update(llm_result)
                    print("  ✓ LLM complete")

                except ImportError:
                    print("  ⚠ LLM enabled but llm_processor not found")
                except Exception as e:
                    print(f"  ⚠ LLM processing failed: {e}")
            else:
                # Add delay when LLM disabled to avoid bot-like behavior
                delay = random.uniform(1.0, 3.0)
                time.sleep(delay)

            # Insert into database
            supabase.table("newsletters").insert(newsletter_data).execute()
            processed_count += 1
            print("  ✓ Stored in database")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed_count += 1
            continue

    print_summary(processed_count, skipped_count, failed_count)


def scrape_all_sources() -> None:
    """Scrape newsletters from all sources with archive URLs"""

    result = (
        supabase.table("sources")
        .select("id, name, newsletter_archive_url")
        .not_.is_("newsletter_archive_url", "null")
        .execute()
    )

    sources = result.data

    if not sources:
        print("No sources with newsletter_archive_url found.")
        return

    print(f"Found {len(sources)} sources with newsletter archives")

    for source in sources:
        source_dict = cast(dict[str, Any], source)
        try:
            process_scraped_newsletters(
                source_id=cast(int, source_dict["id"]), limit=None
            )
        except Exception as e:
            print(f"✗ Error processing source {source_dict['name']}: {e}")
            continue


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        source_id = int(sys.argv[1])
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

        process_scraped_newsletters(source_id, limit)
    else:
        scrape_all_sources()
