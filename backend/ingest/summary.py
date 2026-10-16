from datetime import datetime

from shared.dates import CHICAGO_TIMEZONE


def print_summary(processed: int, skipped: int, failed: int) -> None:
    """Print processing summary."""
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now(CHICAGO_TIMEZONE)}] Processing Complete!")
    print(f"{'=' * 60}")
    print(f"✓ Processed & Stored: {processed}")
    print(f"⊘ Skipped (duplicates): {skipped}")
    print(f"✗ Failed: {failed}")
    print(f"{'=' * 60}\n")
