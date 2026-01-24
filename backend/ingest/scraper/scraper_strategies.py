"""
Scraping strategies for different alderman newsletter archive formats.
Each strategy knows how to extract newsletter links from a specific site structure.
"""

from abc import ABC, abstractmethod
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


class NewsletterArchiveStrategy(ABC):
    """Base strategy for scraping newsletter archives"""

    @abstractmethod
    def extract_newsletters(self, html: str, base_url: str) -> List[Dict[str, str]]:
        """
        Extract newsletter metadata from archive page HTML.

        Returns:
            List of dicts with keys: title, url, date_str (optional)
        """
        pass


class MailChimpArchiveStrategy(NewsletterArchiveStrategy):
    """Strategy for MailChimp-based archives (Ward 1, 2, etc.)"""

    def extract_newsletters(self, html: str, base_url: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        newsletters = []

        # Find newsletter list items (excludes the signup button)
        archive_list = soup.find("ul", id="archive-list")
        if not archive_list:
            return newsletters

        # Only get links within li.campaign elements
        for li in archive_list.find_all("li", class_="campaign"):
            link = li.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "")
            title = link.get("title") or link.get_text(strip=True)
            date_str = self._extract_date_from_context(link)

            newsletters.append({"title": title, "url": href, "date_str": date_str})

        return newsletters

    def _extract_date_from_context(self, link_element) -> str:
        """Extract date from MailChimp archive format: '12/23/2025 - <link>'"""
        parent = link_element.parent
        if parent:
            text = parent.get_text()
            # Match MM/DD/YYYY at start of line
            date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s*-", text)
            if date_match:
                return date_match.group(1)

        return ""


# TODO: Improve this or remove it entirely. May not be useful
class GenericListStrategy(NewsletterArchiveStrategy):
    """Fallback strategy - extract all external links that look like newsletters"""

    def extract_newsletters(self, html: str, base_url: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        newsletters = []

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")

            # Make absolute URL
            absolute_url = urljoin(base_url, href)

            # Skip internal navigation links
            if any(skip in href.lower() for skip in ["#", "javascript:", "mailto:"]):
                continue

            # Look for newsletter-like URLs
            if any(
                keyword in href.lower()
                for keyword in ["newsletter", "archive", "campaign"]
            ):
                title = link.get_text(strip=True)
                newsletters.append(
                    {
                        "title": title or "Untitled Newsletter",
                        "url": absolute_url,
                        "date_str": "",
                    }
                )

        return newsletters


def get_strategy_for_url(url: str) -> NewsletterArchiveStrategy:
    """Select the appropriate scraping strategy based on URL"""

    if "mailchi.mp" in url or "campaign-archive.com" in url:
        return MailChimpArchiveStrategy()
    else:
        return GenericListStrategy()
