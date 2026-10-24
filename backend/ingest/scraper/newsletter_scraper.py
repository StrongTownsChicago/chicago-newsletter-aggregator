"""
Main newsletter scraper - fetches newsletter archives and individual newsletters.
"""

import logging
import time
from typing import cast

import requests
from bs4 import BeautifulSoup

from ingest.email.email_parser import clean_html_content
from ingest.scraper.scraper_strategies import get_strategy_for_url

logger = logging.getLogger(__name__)


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

    def fetch_archive_page(self, url: str) -> str | None:
        """Fetch HTML content of newsletter archive page"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return cast(str, response.text)
            except Exception as e:  # noqa: BLE001  retry loop: any fetch error is retried, then reported
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"  ⚠ Archive fetch failed (attempt {attempt + 1}): {e}"
                    )
                    time.sleep(2**attempt)
                else:
                    logger.error(f"  ✗ Could not fetch archive: {e}")
        return None

    def extract_newsletter_links(self, archive_url: str) -> list[dict[str, str]]:
        """Extract all newsletter links from archive page"""
        logger.info(f"→ Fetching archive: {archive_url}")

        html = self.fetch_archive_page(archive_url)
        if not html:
            return []

        strategy = get_strategy_for_url(archive_url)
        logger.info(f"  Using strategy: {strategy.__class__.__name__}")

        newsletters = strategy.extract_newsletters(html, archive_url)
        logger.info(f"  ✓ Found {len(newsletters)} newsletters")

        return newsletters

    def fetch_newsletter_content(
        self, url: str, title: str, date_str: str
    ) -> dict[str, str] | None:
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

            except Exception as e:  # noqa: BLE001  retry loop: any fetch error is retried, then reported
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"  ⚠ Newsletter fetch failed (attempt {attempt + 1}): {e}"
                    )
                    time.sleep(2**attempt)
                else:
                    logger.error(f"  ✗ Could not fetch newsletter: {url} - {e}")
        return None
