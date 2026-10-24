from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

# The app reasons in Chicago calendar days; console and log timestamps use it too.
CHICAGO_TIMEZONE = ZoneInfo("America/Chicago")


def parse_date_string(date_str: str) -> str | None:
    """Parse various date formats into ISO format; a date without a zone is Chicago's.

    Stored as timestamptz, a zoneless value would be read as UTC midnight, the
    evening before in Chicago.
    """
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CHICAGO_TIMEZONE)
        return str(dt.isoformat())  # Explicit cast to satisfy mypy
    except (ValueError, OverflowError, TypeError):
        return None
