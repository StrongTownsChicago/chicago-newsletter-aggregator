"""Keep library log output out of the test run."""

import logging
import unittest


def quiet_logger(name: str) -> None:
    """Drop the logger's records for the rest of this test module; assertLogs still sees them."""
    logger = logging.getLogger(name)
    handler = logging.NullHandler()
    saved_propagate = logger.propagate
    logger.addHandler(handler)
    logger.propagate = False

    def restore() -> None:
        logger.removeHandler(handler)
        logger.propagate = saved_propagate

    unittest.addModuleCleanup(restore)
