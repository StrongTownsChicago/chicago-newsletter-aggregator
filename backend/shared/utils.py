from datetime import datetime
from dateutil import parser as date_parser

def parse_date_string(date_str: str) -> str | None:
    """Parse various date formats into ISO format"""
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        return dt.isoformat()
    except:
        return None

def print_summary(processed: int, skipped: int, failed: int):
    """Print processing summary"""
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] Processing Complete!")
    print(f"{'='*60}")
    print(f"✓ Processed & Stored: {processed}")
    print(f"⊘ Skipped (duplicates): {skipped}")
    print(f"✗ Failed: {failed}")
    print(f"{'='*60}\n")