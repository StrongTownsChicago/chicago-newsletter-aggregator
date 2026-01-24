"""
Main newsletter scraper - fetches newsletter archives and individual newsletters.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
import time
from ingest.email.email_parser import clean_html_content
from ingest.scraper.scraper_strategies import get_strategy_for_url


class NewsletterScraper:
    """Scrapes newsletter archives and fetches individual newsletters"""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def fetch_archive_page(self, url: str) -> Optional[str]:
        """Fetch HTML content of newsletter archive page"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"  ⚠ Archive fetch failed (attempt {attempt + 1}): {e}")
                    time.sleep(2**attempt)
                else:
                    print(f"  ✗ Could not fetch archive: {e}")
                    return None

    def extract_newsletter_links(self, archive_url: str) -> list[Dict[str, str]]:
        """Extract all newsletter links from archive page"""
        print(f"→ Fetching archive: {archive_url}")

        html = self.fetch_archive_page(archive_url)
        if not html:
            return []

        strategy = get_strategy_for_url(archive_url)
        print(f"  Using strategy: {strategy.__class__.__name__}")

        newsletters = strategy.extract_newsletters(html, archive_url)
        print(f"  ✓ Found {len(newsletters)} newsletters")

        return newsletters

    def fetch_newsletter_content(
        self, url: str, title: str, date_str: str
    ) -> Optional[Dict[str, str]]:
        """Fetch and parse individual newsletter content"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Extract subject/title
                subject = None
                for selector in ["title", "h1", "h2"]:
                    element = soup.find(selector)
                    if element:
                        subject = element.get_text(strip=True)
                        break

                return {
                    "url": url,
                    "html_content": response.text,
                    "plain_text": clean_html_content(response.text),
                    "subject": subject or title or "Untitled Newsletter",
                    "archive_title": title,
                    "archive_date_str": date_str,
                }

            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"  ⚠ Newsletter fetch failed (attempt {attempt + 1}): {e}")
                    time.sleep(2**attempt)
                else:
                    print(f"  ✗ Could not fetch newsletter: {url} - {e}")
                    return None
