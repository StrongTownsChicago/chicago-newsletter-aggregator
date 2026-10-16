"""What every digest module shares: the digest kinds and the site links point to."""

import os
from enum import Enum


class DigestType(Enum):
    """Type of digest email to send."""

    DAILY = "daily"
    WEEKLY = "weekly"


def frontend_base_url() -> str:
    """Get frontend base URL from environment (allows runtime override for tests)."""
    return os.getenv(
        "FRONTEND_BASE_URL", "https://chicago-newsletter-aggregator.open-advocacy.com"
    )
