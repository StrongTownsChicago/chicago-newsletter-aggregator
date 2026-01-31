"""
Error logging utility for notification system.

Logs notification processing errors to timestamped files for debugging.
"""

import os
from datetime import datetime
from typing import Any


def log_notification_error(
    error_type: str, error_message: str, context: dict[str, Any] | None = None
) -> str:
    """
    Log a notification error to a timestamped file.

    Args:
        error_type: Type of error (e.g., 'matching', 'queuing', 'sending')
        error_message: The error message
        context: Optional dictionary with additional context (newsletter_id, user_id, etc.)

    Returns:
        Path to the log file created
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(log_dir, f"notification_error_{timestamp}.txt")

    # Write error to file
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Notification Error Report - {datetime.now()}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Error Type: {error_type}\n")
        f.write(f"Error Message: {error_message}\n\n")

        if context:
            f.write("Context:\n")
            f.write("-" * 60 + "\n")
            for key, value in context.items():
                f.write(f"{key}: {value}\n")

    return filename
