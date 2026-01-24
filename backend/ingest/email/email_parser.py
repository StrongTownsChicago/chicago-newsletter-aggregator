import re
import os
from bs4 import BeautifulSoup
from html2text import html2text
from typing import Dict, Optional

def sanitize_content(content: str, content_type: str, privacy_patterns: dict) -> str:
    """
    Remove privacy-sensitive elements from newsletter content.

    Filters out unsubscribe links, tracking URLs, and sensitive text based on
    provided patterns and PRIVACY_STRIP_PHRASES env var.

    Args:
        content: Raw HTML or plain text content
        content_type: Either 'html' or 'text'
        privacy_patterns: Dict with keys: url_patterns, text_patterns, selectors

    Returns:
        Sanitized content with privacy elements removed
    """
    if not content:
        return ""

    url_patterns = privacy_patterns.get('url_patterns', [])
    text_patterns = privacy_patterns.get('text_patterns', [])
    selectors = privacy_patterns.get('selectors', [])

    if content_type == 'html':
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # 1. Remove by CSS Selector (containers like footers)
            for selector in selectors:
                for match in soup.select(selector):
                    match.decompose()
            
            # 2. Remove <a> tags by URL or Link Text
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(" ", strip=True)
                
                # Check for matches
                matched = False
                for pattern in url_patterns:
                    if re.search(pattern, href, re.IGNORECASE):
                        matched = True
                        break
                
                if not matched:
                    for pattern in text_patterns:
                        if re.search(pattern, text, re.IGNORECASE):
                            matched = True
                            break
                
                if matched:
                    # If the link contains media (images, etc.), unwrap to keep the content
                    if a.find(['img', 'picture', 'svg']):
                        a.unwrap()
                    else:
                        # For purely text links, remove entirely (usually privacy links)
                        a.decompose()
            
            result = str(soup)
            
        except Exception as e:
            print(f"  ⚠️  HTML Sanitization failed: {e}")
            result = content

    elif content_type == 'text':
        # For text, we'll strip lines that look like privacy links or are standalone keywords
        lines = content.splitlines()
        clean_lines = []
        for line in lines:
            # 1. Skip if line contains a known bad URL pattern
            if any(re.search(p, line, re.IGNORECASE) for p in url_patterns):
                continue
            
            # 2. Skip if line is a standalone sensitive keyword (heuristic for plain text links)
            # We wrap the patterns in start/end anchor to ensure we don't catch sentences
            is_standalone_keyword = False
            for pattern in text_patterns:
                # Build a strict line match regex for this pattern
                strict_pattern = rf'^\s*{pattern}\s*$'
                if re.match(strict_pattern, line, re.IGNORECASE):
                    is_standalone_keyword = True
                    break
            
            if is_standalone_keyword:
                continue

            clean_lines.append(line)
        result = '\n'.join(clean_lines)
    else:
        result = content

    # 3. Strip sensitive phrases (names, emails, etc.) from environment variable
    phrases_to_strip = os.environ.get('PRIVACY_STRIP_PHRASES', '').split(',')
    phrases_to_strip = [p.strip() for p in phrases_to_strip if p.strip()]
    
    if phrases_to_strip:
        for phrase in phrases_to_strip:
            # Use escape to ensure any special regex characters don't break things
            pattern = re.escape(phrase)
            result = re.sub(pattern, '[REDACTED]', result, flags=re.IGNORECASE)

    return result

def lookup_source_by_email(from_email: str, supabase_client) -> dict | None:
    """
    Match sender email to source using email_source_mappings table.

    Supports SQL wildcard patterns (e.g., '%@40thward.org') and exact matches.
    Returns full source record with joined data, or None if no match found.
    """
    from_email_lower = from_email.lower()
    
    # Get all mappings with joined source data
    result = supabase_client.table("email_source_mappings") \
        .select("email_pattern, source_id, sources(*)") \
        .execute()
    
    if not result.data:
        return None
    
    # Check each pattern for a match
    for mapping in result.data:
        pattern = mapping['email_pattern'].lower()
        
        # Wildcard pattern (e.g., "%@40thward.org")
        if '%' in pattern:
            # Convert SQL wildcard to regex: % becomes .*
            regex_pattern = pattern.replace('%', '.*').replace('.', r'\.')
            if re.search(regex_pattern, from_email_lower):
                return mapping['sources']
        
        # Exact match or substring match
        elif pattern in from_email_lower or from_email_lower in pattern:
            return mapping['sources']
    
    return None

def extract_name_from_sender(from_address: str) -> Optional[str]:
    """
    Extract display name from email sender field.

    Example: "Alderman John Smith <ward01@example.com>" -> "John Smith"
    Returns None if no display name present.
    """
    # Try parsing display name from email header
    match = re.match(r'^(.+?)\s*<', from_address)
    if match:
        name = match.group(1).strip()
        # Remove quotes if present
        name = name.strip('"').strip("'")
        return name if name else None
    
    return None

def clean_html_content(html: str) -> str:
    """Convert HTML to clean plain text using html2text, removing excessive whitespace."""
    if not html:
        return ""
    
    text = html2text(html)
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_newsletter(msg, supabase_client, privacy_patterns: dict) -> Dict:
    """
    Parse email message into structured newsletter data.

    Args:
        msg: MailMessage object from imap_tools
        supabase_client: Supabase client for database lookups
        privacy_patterns: Dict with privacy filtering patterns (url_patterns, text_patterns, selectors)

    Returns:
        Dictionary with newsletter data ready for database insertion
    """
    
    to_email = msg.to[0] if msg.to else ""
    
    # Look up source using the mapping table
    source = lookup_source_by_email(msg.from_, supabase_client)
    
    # Extract source_id (or None if no match)
    if source:
        source_id = source.get('id')
        print(f"  ✓ Matched to: {source.get('name')} ({source.get('source_type')})")
    else:
        source_id = None
        print(f"  ⚠️  No mapping found for: {msg.from_}")
    
    # Get HTML content (prefer HTML over plain text)
    html_content = msg.html or ""
    plain_text = msg.text or ""
    
    # Sanitize content for Privacy (remove unsubscribe links, etc.)
    # We do this BEFORE converting HTML to text, so the text version is also clean
    if html_content:
        html_content = sanitize_content(html_content, 'html', privacy_patterns)

    if plain_text:
        plain_text = sanitize_content(plain_text, 'text', privacy_patterns)
    
    # If we have HTML but no plain text, convert HTML (now sanitized) to plain text
    if html_content and not plain_text:
        plain_text = clean_html_content(html_content)
    
    return {
        "email_uid": msg.uid,
        "received_date": msg.date.isoformat() if msg.date else None,
        "subject": msg.subject or "(No subject)",
        "from_email": msg.from_,
        "to_email": to_email,
        "source_id": source_id, 
        "raw_html": html_content,
        "plain_text": plain_text
    }