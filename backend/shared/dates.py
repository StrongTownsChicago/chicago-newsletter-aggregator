from datetime import date, datetime
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

# The app reasons in Chicago calendar days; console and log timestamps use it too.
CHICAGO_TIMEZONE = ZoneInfo("America/Chicago")


def parse_date_string(date_str: str) -> str | None:
    """Parse various date formats into ISO format."""
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        return str(dt.isoformat())  # Explicit cast to satisfy mypy
    except (ValueError, OverflowError, TypeError):
        return None


def format_calendar_day(day: date) -> str:
    """A date as the site shows it, e.g. "January 5, 2026"."""
    return f"{day:%B} {day.day}, {day.year}"


def format_received_date(timestamp: str) -> str:
    """A stored timestamp as its Chicago calendar day, e.g. "January 5, 2026".

    Text that isn't an ISO timestamp is returned cut to its first ten characters.
    """
    try:
        moment = datetime.fromisoformat(timestamp)
    except (ValueError, TypeError):
        return timestamp[:10]
    if moment.tzinfo is not None:
        moment = moment.astimezone(CHICAGO_TIMEZONE)
    return format_calendar_day(moment.date())
