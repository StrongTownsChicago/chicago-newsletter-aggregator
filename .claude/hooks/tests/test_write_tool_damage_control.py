"""
Tests for write-tool-damage-control.py

IMPORTANT: These tests validate that the hooks correctly BLOCK writes to protected files.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar


class TestWriteToolDamageControl(unittest.TestCase):
    """Test write tool safety validation."""

    validator_path: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test fixtures."""
        cls.validator_path = (
            Path(__file__).parent.parent / "write-tool-damage-control.py"
        )
        if not cls.validator_path.exists():
            raise FileNotFoundError(f"Validator not found: {cls.validator_path}")

    def validate_write(self, file_path: str) -> tuple[int, str, str]:
        """
        Validate a file write by passing it to the validator as JSON.

        Returns: (exit_code, stdout, stderr)
        """
        hook_input = json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": file_path}}
        )

        result = subprocess.run(
            [sys.executable, str(self.validator_path)],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=5,
        )

        return result.returncode, result.stdout, result.stderr

    def assert_blocked(self, file_path: str, reason_substring: str = "") -> None:
        """Assert that a write is blocked (exit code 2)."""
        exit_code, stdout, stderr = self.validate_write(file_path)
        self.assertEqual(
            exit_code, 2, f"Expected write to be blocked: {file_path}\nstderr: {stderr}"
        )
        if reason_substring:
            self.assertIn(
                reason_substring,
                stderr,
                f"Expected reason substring '{reason_substring}' in: {stderr}",
            )

    def assert_allowed(self, file_path: str) -> None:
        """Assert that a write is allowed (exit code 0)."""
        exit_code, stdout, stderr = self.validate_write(file_path)
        self.assertEqual(
            exit_code, 0, f"Expected write to be allowed: {file_path}\nstderr: {stderr}"
        )

    # ========================================================================
    # ZERO-ACCESS PATHS (Should be BLOCKED)
    # ========================================================================

    def test_blocks_env_file(self) -> None:
        """Block writing .env files."""
        self.assert_blocked(".env", "zero-access path")

    def test_blocks_ssh_keys(self) -> None:
        """Block writing SSH keys."""
        self.assert_blocked("~/.ssh/id_rsa", "zero-access path")

    # ========================================================================
    # READ-ONLY PATHS (Should be BLOCKED)
    # ========================================================================

    def test_blocks_package_lock(self) -> None:
        """Block writing package-lock.json."""
        self.assert_blocked("package-lock.json", "read-only path")

    def test_blocks_yarn_lock(self) -> None:
        """Block writing yarn.lock."""
        self.assert_blocked("yarn.lock", "read-only path")

    def test_blocks_node_modules(self) -> None:
        """Block writing files in node_modules."""
        self.assert_blocked("node_modules/package/index.js", "read-only path")

    def test_blocks_dist_folder(self) -> None:
        """Block writing files in dist/."""
        self.assert_blocked("dist/bundle.js", "read-only path")

    # ========================================================================
    # NO-DELETE PATHS (Should be ALLOWED to write)
    # ========================================================================
    # Note: No-delete paths protect against DELETION.
    # Writes (overwrites) are technically allowed by the hook logic unless specifically blocked

    def test_allows_writing_readme(self) -> None:
        """Allow writing README.md."""
        self.assert_allowed("README.md")

    def test_allows_writing_license(self) -> None:
        """Allow writing LICENSE."""
        self.assert_allowed("LICENSE")

    # ========================================================================
    # NORMAL FILES (Should be ALLOWED)
    # ========================================================================

    def test_allows_normal_source_file(self) -> None:
        """Allow writing normal source code."""
        self.assert_allowed("src/main.py")
        self.assert_allowed("app/components/Button.tsx")


if __name__ == "__main__":
    unittest.main()
