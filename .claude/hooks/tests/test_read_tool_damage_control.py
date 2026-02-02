"""
Tests for read-tool-damage-control.py

IMPORTANT: These tests validate that the hooks correctly BLOCK reads of dangerous files.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar


class TestReadToolDamageControl(unittest.TestCase):
    """Test read tool safety validation."""

    validator_path: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test fixtures."""
        cls.validator_path = (
            Path(__file__).parent.parent / "read-tool-damage-control.py"
        )
        if not cls.validator_path.exists():
            raise FileNotFoundError(f"Validator not found: {cls.validator_path}")

    def validate_read(self, file_path: str) -> tuple[int, str, str]:
        """
        Validate a file read by passing it to the validator as JSON.

        Returns: (exit_code, stdout, stderr)
        """
        hook_input = json.dumps(
            {"tool_name": "Read", "tool_input": {"file_path": file_path}}
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
        """Assert that a read is blocked (exit code 2)."""
        exit_code, stdout, stderr = self.validate_read(file_path)
        self.assertEqual(
            exit_code, 2, f"Expected read to be blocked: {file_path}\nstderr: {stderr}"
        )
        if reason_substring:
            self.assertIn(
                reason_substring,
                stderr,
                f"Expected reason substring '{reason_substring}' in: {stderr}",
            )

    def assert_allowed(self, file_path: str) -> None:
        """Assert that a read is allowed (exit code 0)."""
        exit_code, stdout, stderr = self.validate_read(file_path)
        self.assertEqual(
            exit_code, 0, f"Expected read to be allowed: {file_path}\nstderr: {stderr}"
        )

    # ========================================================================
    # ZERO-ACCESS PATHS (Should be BLOCKED)
    # ========================================================================

    def test_blocks_env_file(self) -> None:
        """Block reading .env files."""
        self.assert_blocked(".env", "zero-access path")

    def test_blocks_env_local(self) -> None:
        """Block reading .env.local files."""
        self.assert_blocked(".env.local", "zero-access path")

    def test_blocks_env_in_subdir(self) -> None:
        """Block reading .env in subdirectories."""
        self.assert_blocked("backend/.env", "zero-access path")

    def test_blocks_ssh_keys(self) -> None:
        """Block reading SSH keys."""
        self.assert_blocked("~/.ssh/id_rsa", "zero-access path")

    def test_blocks_ssh_config(self) -> None:
        """Block reading SSH config."""
        self.assert_blocked("~/.ssh/config", "zero-access path")

    def test_blocks_aws_credentials(self) -> None:
        """Block reading AWS credentials."""
        self.assert_blocked("~/.aws/credentials", "zero-access path")

    def test_blocks_pem_files(self) -> None:
        """Block reading PEM files."""
        self.assert_blocked("server.pem", "zero-access path")
        self.assert_blocked("certs/private.pem", "zero-access path")

    def test_blocks_terraform_state(self) -> None:
        """Block reading Terraform state (contains secrets)."""
        self.assert_blocked("terraform.tfstate", "zero-access path")

    # ========================================================================
    # READ-ONLY PATHS (Should be ALLOWED to read)
    # ========================================================================

    def test_allows_reading_package_lock(self) -> None:
        """Allow reading package-lock.json."""
        self.assert_allowed("package-lock.json")

    def test_allows_reading_system_files(self) -> None:
        """Allow reading system files (like /etc/hosts) generally, unless specifically zero-access."""
        # /etc/ is in readOnlyPaths, so it should be readable.
        self.assert_allowed("/etc/hosts")

    # ========================================================================
    # NO-DELETE PATHS (Should be ALLOWED to read)
    # ========================================================================

    def test_allows_reading_readme(self) -> None:
        """Allow reading README.md."""
        self.assert_allowed("README.md")

    def test_allows_reading_git_config(self) -> None:
        """Allow reading .git/config (in noDeletePaths usually)."""
        # .git/ is in noDeletePaths
        self.assert_allowed(".git/config")

    # ========================================================================
    # NORMAL FILES (Should be ALLOWED)
    # ========================================================================

    def test_allows_normal_source_file(self) -> None:
        """Allow reading normal source code."""
        self.assert_allowed("src/main.py")
        self.assert_allowed("app/components/Header.tsx")


if __name__ == "__main__":
    unittest.main()
