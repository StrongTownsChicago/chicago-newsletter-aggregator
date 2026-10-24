"""
Error logging utility for notification system.

Logs notification processing errors to timestamped files for debugging.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from shared.dates import CHICAGO_TIMEZONE


def log_notification_error(
    error_type: str, error_message: str, context: dict[str, Any] | None = None
) -> str:
    """
    Log a notification error to a timestamped file and return its path.

    `error_type` names the stage (e.g. 'matching', 'queuing', 'sending');
    `context` carries extra details such as newsletter_id or user_id.
    """
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamped filename
    timestamp = datetime.now(CHICAGO_TIMEZONE).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"notification_error_{timestamp}.txt"

    # Write error to file
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"Notification Error Report - {datetime.now(CHICAGO_TIMEZONE)}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Error Type: {error_type}\n")
        f.write(f"Error Message: {error_message}\n\n")

        if context:
            f.write("Context:\n")
            f.write("-" * 60 + "\n")
            f.writelines(f"{key}: {value}\n" for key, value in context.items())

    return str(log_path)
