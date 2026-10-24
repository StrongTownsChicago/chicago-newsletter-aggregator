import os
import re
from typing import Any, cast

from bs4 import BeautifulSoup
from html2text import html2text


def sanitize_content(
    content: str, content_type: str, privacy_patterns: dict[str, Any]
) -> str:
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

    url_patterns = privacy_patterns.get("url_patterns", [])
    text_patterns = privacy_patterns.get("text_patterns", [])
    selectors = privacy_patterns.get("selectors", [])

    if content_type == "html":
        result = _sanitize_html(content, url_patterns, text_patterns, selectors)
    elif content_type == "text":
        result = _sanitize_text(content, url_patterns, text_patterns)
    else:
        result = content

    # 3. Strip sensitive phrases (names, emails, etc.) from environment variable
    phrases_to_strip = os.environ.get("PRIVACY_STRIP_PHRASES", "").split(",")
    return _redact_phrases(result, [p.strip() for p in phrases_to_strip if p.strip()])


def _matches_any(patterns: list[str], value: str) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def _sanitize_html(
    content: str,
    url_patterns: list[str],
    text_patterns: list[str],
    selectors: list[str],
) -> str:
    try:
        soup = BeautifulSoup(content, "html.parser")

        # 1. Remove by CSS Selector (containers like footers)
        for selector in selectors:
            for match in soup.select(selector):
                match.decompose()

        # 2. Remove <a> tags by URL or Link Text
        for a in soup.find_all("a", href=True):
            url_matched = _matches_any(url_patterns, cast(str, a["href"]))
            if _matches_any(text_patterns, a.get_text(" ", strip=True)):
                a.decompose()
            elif url_matched:
                a.unwrap()

        return str(soup)

    except Exception as e:  # noqa: BLE001  sanitizer failure falls back to the original content
        print(f"  ⚠️  HTML Sanitization failed: {e}")
        return content


def _is_standalone_keyword(line: str, text_patterns: list[str]) -> bool:
    """Whether the whole line is one sensitive keyword (a plain-text link), not a sentence."""
    return any(
        re.match(rf"^\s*{pattern}\s*$", line, re.IGNORECASE)
        for pattern in text_patterns
    )


def _sanitize_text(
    content: str, url_patterns: list[str], text_patterns: list[str]
) -> str:
    """Drop lines holding a privacy URL and lines that are a standalone sensitive keyword."""
    return "\n".join(
        line
        for line in content.splitlines()
        if not _matches_any(url_patterns, line)
        and not _is_standalone_keyword(line, text_patterns)
    )


def _redact_phrases(content: str, phrases: list[str]) -> str:
    for phrase in phrases:
        # Escaped so regex characters in a phrase match literally
        content = re.sub(re.escape(phrase), "[REDACTED]", content, flags=re.IGNORECASE)
    return content


SQL_ANY_CHARACTERS_WILDCARD = "%"


def email_matches_pattern(email: str, pattern: str) -> bool:
    """
    Check whether a sender address matches an email_source_mappings pattern.

    The whole address must match the whole pattern (no substring matching),
    case-insensitively, with surrounding whitespace ignored on both sides.
    `%` matches any run of characters (including none), as in SQL LIKE, and
    may appear anywhere in the pattern. Every other character, including
    regex metacharacters such as `.` and `+`, matches only itself.

    The SQL single-character wildcard `_` is deliberately NOT supported:
    underscores legitimately appear in email addresses, so it is treated as
    a literal character.

    Examples:
        email_matches_pattern("info@40thward.org", "%@40thward.org") -> True
        email_matches_pattern("x@40thward.org.evil.io", "%@40thward.org") -> False
        email_matches_pattern("Ward23@CityOfChicago.org", "ward23@cityofchicago.org") -> True
    """
    normalized_email = email.strip()
    normalized_pattern = pattern.strip()
    if not normalized_email or not normalized_pattern:
        return False

    escaped_wildcard = re.escape(SQL_ANY_CHARACTERS_WILDCARD)
    regex_pattern = re.escape(normalized_pattern).replace(escaped_wildcard, ".*")
    return (
        re.fullmatch(regex_pattern, normalized_email, flags=re.IGNORECASE) is not None
    )


def lookup_source_by_email(
    from_email: str, supabase_client: Any
) -> dict[str, Any] | None:
    """
    Match sender email to source using email_source_mappings table.

    Patterns are matched against the full sender address via
    email_matches_pattern() (exact match, or SQL `%` wildcards such as
    '%@40thward.org'). Returns the first matching mapping's source record,
    or None if no match is found.
    """
    # Get all mappings with joined source data
    result = (
        supabase_client.table("email_source_mappings")
        .select("email_pattern, source_id, sources(*)")
        .execute()
    )

    if not result.data:
        return None

    for mapping in result.data:
        mapping_dict = cast(dict[str, Any], mapping)
        pattern = cast(str, mapping_dict["email_pattern"])
        if email_matches_pattern(from_email, pattern):
            return cast(dict[str, Any], mapping_dict["sources"])

    return None


def clean_html_content(html: str) -> str:
    """Convert HTML to clean plain text using html2text, removing excessive whitespace."""
    if not html:
        return ""

    text = html2text(html)
    # Remove excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_newsletter(
    msg: Any, supabase_client: Any, privacy_patterns: dict[str, Any]
) -> dict[str, Any]:
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

    # Extract source_id and ward_number (or None if no match)
    if source:
        source_id = source.get("id")
        ward_number = source.get("ward_number")
        print(f"  ✓ Matched to: {source.get('name')} ({source.get('source_type')})")
    else:
        source_id = None
        ward_number = None
        print(f"  ⚠️  No mapping found for: {msg.from_}")

    # Get HTML content (prefer HTML over plain text)
    html_content = msg.html or ""
    plain_text = msg.text or ""

    # Sanitize content for Privacy (remove unsubscribe links, etc.)
    # We do this BEFORE converting HTML to text, so the text version is also clean
    if html_content:
        html_content = sanitize_content(html_content, "html", privacy_patterns)

    if plain_text:
        plain_text = sanitize_content(plain_text, "text", privacy_patterns)

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
        "ward_number": ward_number,
        "raw_html": html_content,
        "plain_text": plain_text,
    }
