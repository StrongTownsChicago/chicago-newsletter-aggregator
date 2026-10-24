"""Tests for cli/logging_setup.py."""

import io
import logging
import unittest
from unittest.mock import patch

from cli.logging_setup import APP_PACKAGES, configure_cli_logging


class TestConfigureCliLogging(unittest.TestCase):
    def setUp(self) -> None:
        root = logging.getLogger()
        saved_handlers, saved_level = root.handlers[:], root.level
        saved_levels = {name: logging.getLogger(name).level for name in APP_PACKAGES}
        root.handlers.clear()

        def restore() -> None:
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)
            for name, level in saved_levels.items():
                logging.getLogger(name).setLevel(level)

        self.addCleanup(restore)

    def test_app_progress_reaches_stdout_as_bare_messages(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            configure_cli_logging()
            logging.getLogger("processing.llm_client").info("  ✓ Done")

        self.assertEqual(stdout.getvalue(), "  ✓ Done\n")

    def test_other_libraries_stay_quiet_below_warning(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            configure_cli_logging()
            logging.getLogger("httpx").info(
                "HTTP Request: GET https://example.supabase.co"
            )
            logging.getLogger("httpx").warning("retrying")

        self.assertEqual(stdout.getvalue(), "retrying\n")


if __name__ == "__main__":
    unittest.main()
