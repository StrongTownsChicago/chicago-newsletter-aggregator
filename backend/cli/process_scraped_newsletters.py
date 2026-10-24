"""
Scrape newsletters from alderman websites and save to database.
"""

import os
import random
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal, cast

from dotenv import load_dotenv

from cli.ingest_summary import print_summary
from cli.logging_setup import configure_cli_logging
from ingest.scraper.newsletter_scraper import NewsletterScraper
from shared.dates import CHICAGO_TIMEZONE, parse_date_string
from shared.db import get_supabase_client

load_dotenv()

# Configuration
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"
OLLAMA_MODEL = os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "gpt-oss:20b"))

# Initialize clients
supabase = get_supabase_client()
scraper = NewsletterScraper()

ScrapeOutcome = Literal["processed", "skipped", "failed"]

# Random pause ranges (seconds) between archive requests, so runs look less bot-like.
# Duplicates pause too, so a run of them doesn't hammer the archive; the LLM call
# already spaces stored newsletters out, so they pause only when it is off.
DUPLICATE_PAUSE_SECONDS = (1.0, 7.0)
STORE_PAUSE_SECONDS = (1.0, 3.0)


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


def build_newsletter_record(source_id: int, content: dict[str, str]) -> dict[str, Any]:
    """The newsletters row for scraped content; received_date falls back to now."""
    received_date = parse_date_string(content.get("archive_date_str", ""))
    return {
        "source_id": source_id,
        "received_date": received_date or datetime.now(UTC).isoformat(),
        "subject": content["subject"],
        "from_email": None,
        "to_email": None,
        "email_uid": None,
        "raw_html": content["html_content"],
        "plain_text": content["plain_text"],
    }


def add_llm_metadata(newsletter_data: dict[str, Any]) -> None:
    """Merge LLM topics and summary into the row; a failure only warns."""
    try:
        from processing.llm_processor import extract_newsletter_metadata

        print("  LLM processing...")
        llm_result = extract_newsletter_metadata(newsletter_data, OLLAMA_MODEL)
        newsletter_data.update(llm_result)
        print("  ✓ LLM complete")

    except ImportError:
        print("  ⚠ LLM enabled but llm_processor not found")
    except Exception as e:  # noqa: BLE001  optional LLM step must not fail ingestion
        print(f"  ⚠ LLM processing failed: {e}")


def pause_politely(pause_range: tuple[float, float]) -> None:
    """Sleep a random interval within pause_range (seconds)."""
    time.sleep(random.uniform(*pause_range))


def scrape_newsletter(source_id: int, link_info: dict[str, str]) -> ScrapeOutcome:
    """Fetch one archived newsletter and store it unless it is already stored."""
    content = scraper.fetch_newsletter_content(
        link_info["url"], link_info["title"], link_info["date_str"]
    )

    if not content:
        print("  ✗ Failed to fetch content")
        return "failed"

    print(f"  ✓ Retrieved {len(content['plain_text'])} chars")

    if newsletter_exists(source_id, content["subject"]):
        print("  ⊘ Duplicate")
        pause_politely(DUPLICATE_PAUSE_SECONDS)
        return "skipped"

    newsletter_data = build_newsletter_record(source_id, content)

    if ENABLE_LLM:
        add_llm_metadata(newsletter_data)
    else:
        pause_politely(STORE_PAUSE_SECONDS)

    supabase.table("newsletters").insert(newsletter_data).execute()
    print("  ✓ Stored in database")
    return "processed"


def process_scraped_newsletters(source_id: int, limit: int | None = None) -> None:
    """Scrape and process newsletters for a specific source"""

    source_name, archive_url = get_source_archive_url(source_id)

    print(f"\n{'=' * 60}")
    print(
        f"[{datetime.now(CHICAGO_TIMEZONE)}] Scraping newsletters for source ID: {source_id}"
    )
    print(f"Source: {source_name}")
    print(f"Archive URL: {archive_url}")
    print(f"{'=' * 60}\n")

    newsletter_links = scraper.extract_newsletter_links(archive_url)

    if limit:
        newsletter_links = newsletter_links[:limit]

    total = len(newsletter_links)
    outcomes: Counter[ScrapeOutcome] = Counter()

    for i, link_info in enumerate(newsletter_links, 1):
        print(f"\n[{i}/{total}] {link_info['date_str']} - {link_info['title'][:60]}")
        print(f"  URL: {link_info['url']}")

        try:
            outcome = scrape_newsletter(source_id, link_info)
        except Exception as e:  # noqa: BLE001  per-newsletter boundary: log and continue
            print(f"  ✗ Error: {e}")
            outcome = "failed"
        outcomes[outcome] += 1

    print_summary(outcomes["processed"], outcomes["skipped"], outcomes["failed"])


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
        except Exception as e:  # noqa: BLE001  per-source boundary: log and continue
            print(f"✗ Error processing source {source_dict['name']}: {e}")
            continue


if __name__ == "__main__":
    configure_cli_logging()
    import sys

    if len(sys.argv) > 1:
        source_id = int(sys.argv[1])
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

        process_scraped_newsletters(source_id, limit)
    else:
        scrape_all_sources()
