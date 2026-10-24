import os
import re
from typing import Any, cast
from urllib.parse import unquote

from bs4 import BeautifulSoup
from bs4.element import NavigableString
from html2text import html2text

REDACTION_MARKER = "[REDACTED]"


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

    redaction_pattern = build_redaction_pattern(read_strip_phrases())
    url_patterns = privacy_patterns.get("url_patterns", [])
    text_patterns = privacy_patterns.get("text_patterns", [])
    selectors = privacy_patterns.get("selectors", [])

    if content_type == "html":
        try:
            soup = BeautifulSoup(content, "html.parser")

            # 1. Remove by CSS Selector (containers like footers)
            for selector in selectors:
                for match in soup.select(selector):
                    match.decompose()

            # 2. Remove <a> tags by URL or Link Text
            for a in soup.find_all("a", href=True):
                href = normalize_url_for_matching(cast(str, a["href"]))
                text = a.get_text(" ", strip=True)

                url_matched = False
                for pattern in url_patterns:
                    if re.search(pattern, href, re.IGNORECASE):
                        url_matched = True
                        break

                text_matched = False
                for pattern in text_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        text_matched = True
                        break

                if text_matched:
                    a.decompose()
                elif url_matched:
                    a.unwrap()

            # 3. Redact sensitive phrases in text and attribute values, not in markup
            if redaction_pattern:
                redact_html(soup, redaction_pattern)
            return str(soup)

        except Exception as e:  # noqa: BLE001  sanitizer failure falls back to the original content
            print(f"  ⚠️  HTML Sanitization failed: {e}")
            result = content

    elif content_type == "text":
        # For text, we'll strip lines that look like privacy links or are standalone keywords
        lines = content.splitlines()
        clean_lines = []
        for line in lines:
            # 1. Skip if line contains a known bad URL pattern
            matchable_line = normalize_url_for_matching(line)
            if any(re.search(p, matchable_line, re.IGNORECASE) for p in url_patterns):
                continue

            # 2. Skip if line is a standalone sensitive keyword (heuristic for plain text links)
            # We wrap the patterns in start/end anchor to ensure we don't catch sentences
            is_standalone_keyword = False
            for pattern in text_patterns:
                # Build a strict line match regex for this pattern
                strict_pattern = rf"^\s*{pattern}\s*$"
                if re.match(strict_pattern, line, re.IGNORECASE):
                    is_standalone_keyword = True
                    break

            if is_standalone_keyword:
                continue

            clean_lines.append(line)
        result = "\n".join(clean_lines)
    else:
        result = content

    # 3. Redact sensitive phrases (names, emails, etc.)
    if redaction_pattern:
        result = redaction_pattern.sub(REDACTION_MARKER, result)
    return result


def normalize_url_for_matching(url: str) -> str:
    """
    Return the URL a browser would follow, for matching against privacy patterns.

    Browsers drop ASCII tabs and newlines anywhere in a URL and surrounding
    whitespace, and percent-escapes reach the server decoded, so
    "list-man<TAB>age.com/un%73ubscribe" is still an unsubscribe link.
    """
    return unquote(re.sub(r"[\t\n\r]", "", url).strip())


def read_strip_phrases() -> list[str]:
    """Return the phrases to redact, from the PRIVACY_STRIP_PHRASES env var."""
    phrases = os.environ.get("PRIVACY_STRIP_PHRASES", "").split(",")
    return [phrase.strip() for phrase in phrases if phrase.strip()]


def build_redaction_pattern(phrases: list[str]) -> re.Pattern[str] | None:
    """
    Compile one case-insensitive pattern matching any phrase to redact.

    The marker itself is the first alternative, so already redacted text is
    replaced with itself: a phrase such as "Ted" never rewrites the "TED" in an
    earlier marker, and sanitizing stored content again changes nothing.
    Longer phrases come first, so "Jane Roe" is redacted whole before "Jane".
    Phrases match whole words only: "Ted" redacts "Ted's" but not "started".
    """
    if not phrases:
        return None
    alternatives = [
        re.escape(REDACTION_MARKER),
        *(
            whole_word_regex(phrase)
            for phrase in sorted(phrases, key=len, reverse=True)
        ),
    ]
    return re.compile("|".join(alternatives), re.IGNORECASE)


def whole_word_regex(phrase: str) -> str:
    """Escape phrase, refusing to match where its first or last letter continues a word."""
    escaped = re.escape(phrase)
    starts_with_word = re.match(r"\w", phrase) is not None
    ends_with_word = re.match(r"\w", phrase[-1]) is not None
    return (
        (r"(?<!\w)" if starts_with_word else "")
        + escaped
        + (r"(?!\w)" if ends_with_word else "")
    )


def redact_html(soup: BeautifulSoup, pattern: re.Pattern[str]) -> None:
    """Redact text, comments and attribute values in place; tag and attribute names stay intact.

    Only changed values are reassigned, so a phrase list that matches nothing
    leaves the output as it was without one.
    """
    redact_visible_text(soup, pattern)
    # Every string on its own too: comments, CDATA and script text are not part
    # of the visible text, and joining text can hide a phrase that sits alone in
    # its node ("a" from an unwrapped link + "<p>Jane Doe</p>" reads "aJane").
    for string in soup.find_all(string=True):
        redacted = pattern.sub(REDACTION_MARKER, string)
        if redacted != string:
            # Same class, so comments and CDATA stay comments and CDATA.
            string.replace_with(type(string)(redacted))
    for tag in soup.find_all(True):
        for name, value in list(tag.attrs.items()):
            # Multi-valued attributes (class, rel) are redacted as written, so a
            # phrase spanning two tokens ("Jane Doe") still matches.
            original = value if isinstance(value, str) else " ".join(value)
            redacted = pattern.sub(REDACTION_MARKER, original)
            if redacted != original:
                tag[name] = redacted


def redact_visible_text(soup: BeautifulSoup, pattern: re.Pattern[str]) -> None:
    """
    Redact phrases in the document's visible text, even when split across tags.

    The text nodes are matched as one string in document order, so "Jane
    <b>Doe</b>" and text left either side of a removed link are caught. Each
    match leaves the marker in the node where it starts and removes the rest
    from the nodes it spans. Text of neighbouring blocks is joined too, so a
    phrase running from one block into the next is also redacted.
    """
    nodes = [
        node for node in soup.find_all(string=True) if type(node) is NavigableString
    ]
    text = "".join(nodes)
    match_spans = [
        match.span()
        for match in pattern.finditer(text)
        if match.group().upper() != REDACTION_MARKER
    ]
    if not match_spans:
        return

    node_start = 0
    for node in nodes:
        node_end = node_start + len(node)
        redacted = redact_span(text, node_start, node_end, match_spans)
        if redacted != node:
            node.replace_with(NavigableString(redacted))
        node_start = node_end


def redact_span(
    text: str, start: int, end: int, match_spans: list[tuple[int, int]]
) -> str:
    """Return text[start:end] with the parts covered by match_spans redacted."""
    pieces: list[str] = []
    position = start
    for match_start, match_end in match_spans:
        if match_end <= start or match_start >= end:
            continue
        pieces.append(text[position : max(position, match_start)])
        # The marker goes where the match starts; later nodes only lose their part.
        if match_start >= start:
            pieces.append(REDACTION_MARKER)
        position = max(position, min(end, match_end))
    pieces.append(text[position:end])
    return "".join(pieces)


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
