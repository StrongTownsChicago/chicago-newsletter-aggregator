"""
Scrape newsletters from alderman websites and save to database.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from ingest.scraper.process_scraped import NewsletterScraper
from shared.db import get_supabase_client
from shared.utils import parse_date_string, print_summary

load_dotenv()

# Configuration
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"

# Initialize clients
supabase = get_supabase_client()
scraper = NewsletterScraper()


def newsletter_exists(source_id: int, subject: str) -> bool:
    """Check if newsletter already processed using source_id + subject + date"""
    result = supabase.table("newsletters") \
        .select("id") \
        .eq("source_id", source_id) \
        .eq("subject", subject) \
        .execute()
    return len(result.data) > 0

def process_scraped_newsletters(source_id: int, archive_url: str, limit: int | None = None):
    """
    Scrape and process newsletters for a specific source.
    
    Args:
        source_id: Database ID of the alderman/source
        archive_url: URL of their newsletter archive
        limit: Max newsletters to process (None = all)
    """
    
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] Scraping newsletters for source ID: {source_id}")
    print(f"Archive URL: {archive_url}")
    print(f"{'='*60}\n")
    
    # Scrape newsletters
    newsletters = scraper.scrape_archive(archive_url, limit=limit)
    
    processed_count = 0
    skipped_count = 0
    failed_count = 0
    
    for newsletter_content in newsletters:
        try:
            url = newsletter_content['url']
            
            # Skip if already processed
            if newsletter_exists(source_id, newsletter_content['subject']):
                print(f"⊘ Duplicate: {url}")
                skipped_count += 1
                continue
            
            # Parse date
            received_date = parse_date_string(newsletter_content.get('archive_date_str', ''))
            
            # Build newsletter record
            newsletter_data = {
                "source_id": source_id,
                "received_date": received_date or datetime.now().isoformat(),
                "subject": newsletter_content['subject'],
                "from_email": None,  # Not applicable for scraped newsletters
                "to_email": None,
                "email_uid": None,   # Not applicable
                "raw_html": newsletter_content['html_content'],
                "plain_text": newsletter_content['plain_text'],
            }
            
            # Optional: LLM processing
            if ENABLE_LLM:
                try:
                    from processing.llm_processor import process_with_ollama
                    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
                    
                    print(f"Processing: {newsletter_data['subject']}")
                    llm_result = process_with_ollama(newsletter_data, OLLAMA_MODEL)
                    newsletter_data.update(llm_result)
                    
                except ImportError:
                    print(f"  Warning: LLM enabled but llm_processor not found")
                except Exception as e:
                    print(f"  Warning: LLM processing failed: {e}")
            
            # Insert into database
            supabase.table("newsletters").insert(newsletter_data).execute()
            processed_count += 1
            print(f"  ✓ Stored: {newsletter_data['subject'][:50]}...")
            
        except Exception as e:
            print(f"✗ Error processing newsletter: {e}")
            failed_count += 1
            continue
    
    print_summary(processed_count, skipped_count, failed_count)

def scrape_all_sources():
    """Scrape newsletters from all sources that have archive_url set"""
    
    # Get all sources with newsletter archives
    result = supabase.table("sources") \
        .select("id, name, newsletter_archive_url") \
        .not_.is_("newsletter_archive_url", "null") \
        .execute()
    
    sources = result.data
    
    if not sources:
        print("No sources with newsletter_archive_url found.")
        return
    
    print(f"Found {len(sources)} sources with newsletter archives")
    
    for source in sources:
        try:
            process_scraped_newsletters(
                source_id=source['id'],
                archive_url=source['newsletter_archive_url'],
                limit=None  # Process all
            )
        except Exception as e:
            print(f"✗ Error processing source {source['name']}: {e}")
            continue


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Manual mode: python scrape_newsletters.py <source_id> <archive_url> [limit]
        source_id = int(sys.argv[1])
        archive_url = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
        
        process_scraped_newsletters(source_id, archive_url, limit)
    else:
        # Auto mode: scrape all sources with archive URLs
        scrape_all_sources()