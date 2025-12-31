import re
from html2text import html2text
from typing import Dict, Optional

def lookup_source_by_email(from_email: str, supabase_client) -> dict | None:
    """
    Find source by matching email against mappings table with wildcard support.
    Returns the full source record if found, None otherwise.
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
    Attempt to extract name from email sender field.
    Example: "Alderman John Smith <ward01@example.com>" -> "John Smith"
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
    """Convert HTML to clean plain text"""
    if not html:
        return ""
    
    text = html2text(html)
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_newsletter(msg, supabase_client) -> Dict:
    """
    Parse email message into structured newsletter data.
    
    Args:
        msg: MailMessage object from imap_tools
        supabase_client: Supabase client for database lookups
        
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
    
    # If we have HTML but no plain text, convert HTML to plain text
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