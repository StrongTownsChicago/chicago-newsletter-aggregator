"""Logging for command-line entry points."""

import logging
import sys

# Packages whose progress messages a CLI run shows; other libraries stay at WARNING.
APP_PACKAGES = ("ingest", "notifications", "processing")


def configure_cli_logging() -> None:
    """Print log records as bare messages on stdout, in order with the CLI's own output."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
    for package in APP_PACKAGES:
        logging.getLogger(package).setLevel(logging.INFO)
