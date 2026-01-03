"""
Main newsletter scraper - fetches newsletter archives and individual newsletters.
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
from ingest.email.email_parser import clean_html_content
from ingest.scraper.scraper_strategies import get_strategy_for_url


class NewsletterScraper:
    """Scrapes newsletter archives and fetches individual newsletters"""
    
    def __init__(self, max_retries: int = 3, delay_between_requests: float = 1.0):
        self.max_retries = max_retries
        self.delay = delay_between_requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
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
                    time.sleep(2 ** attempt)
                else:
                    print(f"  ✗ Could not fetch archive: {e}")
                    return None
    
    def extract_newsletter_links(self, archive_url: str) -> List[Dict[str, str]]:
        """
        Extract all newsletter links from an archive page.
        
        Returns:
            List of dicts with keys: title, url, date_str
        """
        print(f"→ Fetching archive: {archive_url}")
        
        html = self.fetch_archive_page(archive_url)
        if not html:
            return []
        
        # Select appropriate strategy
        strategy = get_strategy_for_url(archive_url)
        print(f"  Using strategy: {strategy.__class__.__name__}")
        
        newsletters = strategy.extract_newsletters(html, archive_url)
        print(f"  ✓ Found {len(newsletters)} newsletters")
        
        return newsletters
    
    def fetch_newsletter_content(self, url: str) -> Optional[Dict[str, str]]:
        """
        Fetch and parse individual newsletter content.
        
        Returns:
            Dict with keys: url, html_content, plain_text, subject
        """
        for attempt in range(self.max_retries):
            try:
                time.sleep(self.delay)  # Rate limiting
                
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract subject/title
                subject = None
                for selector in ['title', 'h1', 'h2']:
                    element = soup.find(selector)
                    if element:
                        subject = element.get_text(strip=True)
                        break
                
                # Get full HTML
                html_content = response.text
                
                # Convert to plain text
                plain_text = clean_html_content(html_content)
                
                return {
                    'url': url,
                    'html_content': html_content,
                    'plain_text': plain_text,
                    'subject': subject or 'Untitled Newsletter'
                }
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"  ⚠ Newsletter fetch failed (attempt {attempt + 1}): {e}")
                    time.sleep(2 ** attempt)
                else:
                    print(f"  ✗ Could not fetch newsletter: {url} - {e}")
                    return None
    
    def scrape_archive(self, archive_url: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Scrape all newsletters from an archive page.
        
        Args:
            archive_url: URL of the newsletter archive page
            limit: Maximum number of newsletters to fetch (None = all)
            
        Returns:
            List of newsletter content dicts
        """
        # Get all newsletter links
        newsletter_links = self.extract_newsletter_links(archive_url)
        
        if limit:
            newsletter_links = newsletter_links[:limit]
        
        # Fetch each newsletter
        newsletters = []
        for i, link_info in enumerate(newsletter_links, 1):
            print(f"\n[{i}/{len(newsletter_links)}] {link_info['date_str']} - {link_info['title'][:60]}")
            print(f"  URL: {link_info['url']}")
            
            
            content = self.fetch_newsletter_content(link_info['url'])
            if content:
                # Merge link metadata with content
                content.update({
                    'archive_title': link_info['title'],
                    'archive_date_str': link_info['date_str']
                })
                newsletters.append(content)
                print(f"  ✓ Retrieved {len(content['plain_text'])} chars")
            else:
                print(f"  ✗ Failed to fetch content")
        
        return newsletters


def test_scraper():
    """Test the scraper with Ward 1 and Ward 2"""
    scraper = NewsletterScraper()
    
    # Test Ward 1
    print("=" * 60)
    print("Testing Ward 1 Archive")
    print("=" * 60)
    ward1_newsletters = scraper.scrape_archive(
        "https://us4.campaign-archive.com/home/?u=e4d2e8115e36fe98f1fbf8f5f&id=218af5f0b5",
        limit=3  # Just test with 3
    )
    print(f"\n✓ Retrieved {len(ward1_newsletters)} newsletters from Ward 1")
    
    # Test Ward 2
    print("\n" + "=" * 60)
    print("Testing Ward 2 Archive")
    print("=" * 60)
    ward2_newsletters = scraper.scrape_archive(
        "https://us11.campaign-archive.com/home/?u=936879b99e79c41d6215b423f&id=3a38d3733c",
        limit=3
    )
    print(f"\n✓ Retrieved {len(ward2_newsletters)} newsletters from Ward 2")


if __name__ == "__main__":
    test_scraper()