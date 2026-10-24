"""
Allowlist sanitizer for stored newsletter HTML.

The frontend renders raw_html into its own pages, and that HTML comes from
email senders and scraped archives, so only presentational markup is kept:
no scripts, event handlers, forms, frames, <style> blocks or javascript: URLs.
`class` and `id` are dropped too, so a newsletter can't reuse the site's own
CSS classes (a full-page overlay) or clobber DOM globals by id.
"""

import re

import nh3

# nh3's defaults (formatting, lists, tables, images, links) plus markup common
# in email layouts. Not allowed: form controls, iframe, object, svg, math, style.
ALLOWED_TAGS = nh3.ALLOWED_TAGS | {"font", "tfoot"}

# Removed with their content: their text is code or page metadata, never newsletter text.
CONTENT_STRIPPED_TAGS = {"script", "style", "title", "template", "noscript"}

# Legacy table attributes that email layouts still rely on.
LAYOUT_ATTRIBUTES = {
    "align",
    "valign",
    "width",
    "height",
    "bgcolor",
    "border",
    "cellpadding",
    "cellspacing",
}
GENERIC_ATTRIBUTES = LAYOUT_ATTRIBUTES | {"style", "title", "dir", "lang"}

ALLOWED_ATTRIBUTES = {
    tag: attributes | GENERIC_ATTRIBUTES
    for tag, attributes in {
        **{tag: set() for tag in ALLOWED_TAGS},
        **nh3.ALLOWED_ATTRIBUTES,
        "font": {"color", "face", "size"},
    }.items()
    if tag in ALLOWED_TAGS
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}

# Inline CSS a newsletter needs for its own layout. Positioning (position,
# top, left, z-index, transform) is left out, and margins may not be negative
# (see keep_style_declaration), so content can't be placed over the site's
# header or controls.
ALLOWED_STYLE_PROPERTIES = {
    "background",
    "background-color",
    "background-image",
    "background-position",
    "background-repeat",
    "background-size",
    "border",
    "border-bottom",
    "border-collapse",
    "border-color",
    "border-left",
    "border-radius",
    "border-right",
    "border-spacing",
    "border-style",
    "border-top",
    "border-width",
    "color",
    "display",
    "font",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "height",
    "letter-spacing",
    "line-height",
    "list-style",
    "list-style-type",
    "margin",
    "margin-bottom",
    "margin-left",
    "margin-right",
    "margin-top",
    "max-height",
    "max-width",
    "min-height",
    "min-width",
    "padding",
    "padding-bottom",
    "padding-left",
    "padding-right",
    "padding-top",
    "table-layout",
    "text-align",
    "text-decoration",
    "text-transform",
    "vertical-align",
    "white-space",
    "width",
    "word-break",
    "word-wrap",
}

# A plain property name: no comments or escapes that could disguise another property.
STYLE_PROPERTY_NAME = re.compile(r"-?[a-z][a-z-]*")
# One to four non-negative margin lengths ("0 auto", "10px 0"), as email layouts use.
MARGIN_VALUE = re.compile(
    r"(?:\s*(?:auto|0|\d+(?:\.\d+)?(?:px|em|rem|%|pt))\s*){1,4}(?:!\s*important\s*)?",
    re.IGNORECASE,
)


def keep_style_declaration(declaration: str) -> bool:
    """Whether one "property: value" declaration of a style attribute may stay."""
    name, separator, value = declaration.partition(":")
    if not separator:
        return not declaration.strip()
    name = name.strip().lower()
    if not STYLE_PROPERTY_NAME.fullmatch(name):
        return False
    return not name.startswith("margin") or MARGIN_VALUE.fullmatch(value) is not None


def filter_attribute(_tag: str, attribute: str, value: str) -> str | None:
    """nh3 attribute filter: drop style declarations that could move content over the site."""
    if attribute != "style":
        return value
    return ";".join(
        declaration
        for declaration in value.split(";")
        if keep_style_declaration(declaration)
    )


_CLEANER = nh3.Cleaner(
    tags=ALLOWED_TAGS,
    clean_content_tags=CONTENT_STRIPPED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    url_schemes=ALLOWED_URL_SCHEMES,
    filter_style_properties=ALLOWED_STYLE_PROPERTIES,
    attribute_filter=filter_attribute,
    strip_comments=True,
)


def sanitize_markup(html: str) -> str:
    """Return html with everything outside the allowlist removed; safe to render as-is."""
    return _CLEANER.clean(html) if html else ""
