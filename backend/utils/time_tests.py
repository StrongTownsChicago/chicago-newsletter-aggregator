"""
Performance Profiling Utility for Backend Tests

This script discovers and runs all backend tests while timing individual test
execution. It outputs the top 20 slowest tests to help identify performance
bottlenecks in the test suite.

Usage:
    uv run python utils/time_tests.py
"""

import unittest
import time
import sys
from pathlib import Path
from typing import Any

# Add the backend directory to sys.path to resolve local imports correctly
backend_root = Path(__file__).parent.parent.absolute()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


class TimingResult(unittest.TextTestResult):
    """Custom TestResult that records the duration of each test."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.recorded_durations: list[tuple[str, float]] = []
        self._start_time: float = 0.0

    def startTest(self, test: unittest.TestCase) -> None:
        self._start_time = time.time()
        super().startTest(test)

    def stopTest(self, test: unittest.TestCase) -> None:
        duration = time.time() - self._start_time
        self.recorded_durations.append((str(test), duration))
        super().stopTest(test)


class TimingRunner(unittest.TextTestRunner):
    """Custom TestRunner that uses TimingResult and prints slow tests."""

    def _makeResult(self) -> TimingResult:
        # Override _makeResult to return our custom TimingResult
        return TimingResult(self.stream, self.descriptions, self.verbosity)

    def run(self, test: unittest.TestSuite | unittest.TestCase) -> Any:
        # We call super().run which returns a TestResult
        result = super().run(test)

        # Ensure result is our TimingResult before accessing durations
        if isinstance(result, TimingResult):
            # Sort by duration descending and display top 20
            self.stream.writeln("\nTop 20 Slowest Tests:")
            self.stream.writeln("=" * 60)
            sorted_durations = sorted(
                result.recorded_durations, key=lambda x: x[1], reverse=True
            )
            for name, duration in sorted_durations[:20]:
                self.stream.writeln(f"{duration:7.3f}s : {name}")
            self.stream.writeln("=" * 60)

        return result


if __name__ == "__main__":
    # Ensure we are running from the backend directory
    os_cwd = Path.cwd()
    if (os_cwd / "tests").exists():
        loader = unittest.TestLoader()
        suite = loader.discover("tests")
        runner = TimingRunner(verbosity=1)
        runner.run(suite)
    else:
        print(f"Error: Could not find 'tests' directory in {os_cwd}")
        print("Please run this script from the 'backend' root directory.")
        sys.exit(1)
