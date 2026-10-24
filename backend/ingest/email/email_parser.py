import logging
import os
import re
from typing import Any, cast
from urllib.parse import unquote

from bs4 import BeautifulSoup
from bs4.element import NavigableString
from html2text import html2text

from ingest.markup_sanitizer import sanitize_markup

logger = logging.getLogger(__name__)

REDACTION_MARKER = "[REDACTED]"
# Joins text nodes for matching: a private-use character, so never newsletter text.
NODE_SEPARATOR = "\ue000"
# A letter beside a phrase means the phrase is part of a longer word.
LETTER = r"[^\W\d_]"


def sanitize_content(
    content: str, content_type: str, privacy_patterns: dict[str, Any]
) -> str:
    """
    Remove privacy-sensitive elements from newsletter content.

    Filters out unsubscribe links, tracking URLs, and sensitive text based on
    `privacy_patterns` (keys: url_patterns, text_patterns, selectors) and the
    PRIVACY_STRIP_PHRASES env var. `content_type` is 'html' or 'text'.
    Privacy only: pass HTML through `sanitize_markup()` before storing it.
    """
    if not content:
        return ""

    redaction_pattern = build_redaction_pattern(read_strip_phrases())
    url_patterns = privacy_patterns.get("url_patterns", [])
    text_patterns = privacy_patterns.get("text_patterns", [])
    selectors = privacy_patterns.get("selectors", [])

    if content_type == "html":
        return _sanitize_html(
            content, url_patterns, text_patterns, selectors, redaction_pattern
        )
    if content_type == "text":
        result = _sanitize_text(content, url_patterns, text_patterns)
    else:
        result = content

    # 3. Redact sensitive phrases (names, emails, etc.)
    return redact_text(result, redaction_pattern)


def sanitize_newsletter_html(html: str, privacy_patterns: dict[str, Any]) -> str:
    """
    Return newsletter HTML as stored: safe to render and privacy-sanitized.

    Markup is sanitized first, so privacy redaction sees the document as a
    browser parses it (text moved out of tables, NULs dropped) and the joined
    text can't hide a phrase; it runs again last, so the result is its output.
    """
    return sanitize_markup(
        sanitize_content(sanitize_markup(html), "html", privacy_patterns)
    )


def _matches_any(patterns: list[str], value: str) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def _sanitize_html(
    content: str,
    url_patterns: list[str],
    text_patterns: list[str],
    selectors: list[str],
    redaction_pattern: re.Pattern[str] | None,
) -> str:
    try:
        soup = BeautifulSoup(content, "html.parser")

        # 1. Remove by CSS Selector (containers like footers)
        for selector in selectors:
            for match in soup.select(selector):
                match.decompose()

        # 2. Remove <a> tags by URL or Link Text
        for a in soup.find_all("a", href=True):
            url_matched = _matches_any(
                url_patterns, normalize_url_for_matching(cast(str, a["href"]))
            )
            if _matches_any(text_patterns, a.get_text(" ", strip=True)):
                a.decompose()
            elif url_matched:
                a.unwrap()

        # 3. Redact sensitive phrases in text and attribute values, not in markup
        if redaction_pattern:
            redact_html(soup, redaction_pattern)
        return str(soup)

    except Exception as e:  # noqa: BLE001  sanitizer failure falls back to the original content
        logger.warning(f"  ⚠️  HTML Sanitization failed: {e}")
        return redact_text(content, redaction_pattern)


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
        if not _matches_any(url_patterns, normalize_url_for_matching(line))
        and not _is_standalone_keyword(line, text_patterns)
    )


def redact_text(content: str, pattern: re.Pattern[str] | None) -> str:
    """Replace every phrase pattern matches with the redaction marker."""
    return pattern.sub(REDACTION_MARKER, content) if pattern else content


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

    The marker itself is the first alternative (group "marker"), so already
    redacted text is replaced with itself: a phrase such as "Ted" never
    rewrites the "TED" in an earlier marker, and sanitizing stored content
    again changes nothing. Longer phrases come first, so "Jane Roe" is
    redacted whole before "Jane".
    """
    if not phrases:
        return None
    alternatives = [
        f"(?P<marker>{re.escape(REDACTION_MARKER)})",
        *(phrase_regex(phrase) for phrase in sorted(phrases, key=len, reverse=True)),
    ]
    return re.compile("|".join(alternatives), re.IGNORECASE)


def phrase_regex(phrase: str) -> str:
    """
    Return the regex for one phrase.

    A letter right before or after the phrase means it is part of a longer
    word, so "Ted" matches "Ted", "Ted's" and "_Ted_" but not "started".
    Digits and underscores don't count: "3125551234" still matches
    "+13125551234". Whitespace matches any run of whitespace, as a browser
    renders a name wrapped across source lines, and NODE_SEPARATOR may appear
    anywhere, so a phrase split by tags ("Jane <b>Doe</b>") still matches.
    """
    separators = re.escape(NODE_SEPARATOR) + "*"
    whitespace = rf"[\s{re.escape(NODE_SEPARATOR)}]+"
    body = whitespace.join(
        separators.join(re.escape(character) for character in word)
        for word in phrase.split()
    )
    before = rf"(?<!{LETTER})" if re.match(LETTER, phrase) else ""
    after = rf"(?!{LETTER})" if re.match(LETTER, phrase[-1]) else ""
    return before + body + after


def redact_html(soup: BeautifulSoup, pattern: re.Pattern[str]) -> None:
    """Redact text, comments and attribute values in place; tag and attribute names stay intact.

    Only changed values are reassigned, so a phrase list that matches nothing
    leaves the output as it was without one.
    """
    redact_visible_text(soup, pattern)
    for string in soup.find_all(string=True):
        # Comments, CDATA and script or style text are not visible text, so each
        # is redacted on its own.
        if type(string) is NavigableString:
            continue
        redacted = pattern.sub(REDACTION_MARKER, string)
        if redacted != string:
            # Same class, so comments and CDATA stay comments and CDATA.
            string.replace_with(type(string)(redacted))
    for tag in soup.find_all(True):
        for name, value in list(tag.attrs.items()):
            # Multi-valued attributes (class, rel) are redacted as written, so a
            # phrase spanning two tokens ("Jane Doe") still matches.
            original = value if isinstance(value, str) else " ".join(value)
            redacted = redact_attribute_value(original, pattern)
            if redacted != original:
                tag[name] = redacted


def redact_attribute_value(value: str, pattern: re.Pattern[str]) -> str:
    """Redact an attribute value, also as percent-decoded ("mailto:jane%40doe.com")."""
    redacted = pattern.sub(REDACTION_MARKER, value)
    if redacted != value:
        return redacted
    decoded = unquote(value)
    redacted_decoded = pattern.sub(REDACTION_MARKER, decoded)
    return redacted_decoded if redacted_decoded != decoded else value


def redact_visible_text(soup: BeautifulSoup, pattern: re.Pattern[str]) -> None:
    """
    Redact phrases in the document's visible text, even when split across tags.

    The text nodes are matched as one string in document order, joined by
    NODE_SEPARATOR: a phrase may span it ("Jane <b>Doe</b>", or text left
    either side of a removed link), and it ends a word, so a block ending in
    a letter ("<p>Contact</p><p>Jane Doe</p>") doesn't hide the next phrase.
    Each match leaves the marker in the node where it starts and removes the
    rest from the nodes it spans.
    """
    nodes = [
        node for node in soup.find_all(string=True) if type(node) is NavigableString
    ]
    text = NODE_SEPARATOR.join(nodes)
    match_spans = [
        match.span()
        for match in pattern.finditer(text)
        if match.group("marker") is None
    ]
    if not match_spans:
        return

    first_span = 0
    node_start = 0
    for node in nodes:
        node_end = node_start + len(node)
        # Nodes and spans are both in document order, so skipped spans never return.
        while (
            first_span < len(match_spans) and match_spans[first_span][1] <= node_start
        ):
            first_span += 1
        redacted = redact_node_text(text, node_start, node_end, match_spans, first_span)
        if redacted != node:
            node.replace_with(
                NavigableString(collapse_like_parser(redacted, node, soup))
            )
        node_start = node_end + len(NODE_SEPARATOR)


def collapse_like_parser(text: str, node: NavigableString, soup: BeautifulSoup) -> str:
    """
    Collapse whitespace-only text the way BeautifulSoup does when it parses.

    Redaction can leave a node with only spaces; the next parse would turn
    them into one space or newline, so a second sanitize would change the
    output. Whitespace stays as written inside <pre> and <textarea>.
    """
    if not text or any(character not in soup.ASCII_SPACES for character in text):
        return text
    preserving_tags = soup.builder.preserve_whitespace_tags
    if any(parent.name in preserving_tags for parent in node.parents):
        return text
    return "\n" if "\n" in text else " "


def redact_node_text(
    text: str,
    start: int,
    end: int,
    match_spans: list[tuple[int, int]],
    first_span: int,
) -> str:
    """Return text[start:end] with the parts covered by match_spans redacted.

    Spans before first_span end before start; spans are scanned only while
    they begin before end.
    """
    pieces: list[str] = []
    position = start
    for match_start, match_end in (
        match_spans[index] for index in range(first_span, len(match_spans))
    ):
        if match_start >= end:
            break
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

    The whole address must match the whole pattern, case-insensitively, with
    surrounding whitespace ignored. `%` matches any run of characters (even
    none), anywhere in the pattern, as in SQL LIKE. Every other character,
    including `.` and `+`, matches only itself; `_` is a literal, not SQL's
    wildcard, because underscores legitimately appear in email addresses.
    E.g. "%@40thward.org" matches "info@40thward.org", not "x@40thward.org.evil.io".
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
    Parse an imap_tools MailMessage into a newsletter row ready for insertion.

    `supabase_client` is used for the sender-to-source lookup; `privacy_patterns`
    is passed to `sanitize_content()`.
    """

    to_email = msg.to[0] if msg.to else ""

    # Look up source using the mapping table
    source = lookup_source_by_email(msg.from_, supabase_client)

    # Extract source_id and ward_number (or None if no match)
    if source:
        source_id = source.get("id")
        ward_number = source.get("ward_number")
        logger.info(
            f"  ✓ Matched to: {source.get('name')} ({source.get('source_type')})"
        )
    else:
        source_id = None
        ward_number = None
        logger.warning(f"  ⚠️  No mapping found for: {msg.from_}")

    # Get HTML content (prefer HTML over plain text)
    html_content = msg.html or ""
    plain_text = msg.text or ""

    # Keep only markup that is safe to render and sanitize for privacy (remove
    # unsubscribe links, etc.). We do this BEFORE converting HTML to text, so
    # the text version is also clean
    if html_content:
        html_content = sanitize_newsletter_html(html_content, privacy_patterns)

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
