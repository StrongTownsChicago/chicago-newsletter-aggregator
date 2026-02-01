"""
Tests for edit-tool-damage-control.py

IMPORTANT: These tests validate that the hooks correctly BLOCK edits to protected files.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar


class TestEditToolDamageControl(unittest.TestCase):
    """Test edit tool safety validation."""

    validator_path: ClassVar[Path]

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.validator_path = Path(__file__).parent.parent / "edit-tool-damage-control.py"
        if not cls.validator_path.exists():
            raise FileNotFoundError(f"Validator not found: {cls.validator_path}")

    def validate_edit(self, file_path: str) -> tuple[int, str, str]:
        """
        Validate a file edit by passing it to the validator as JSON.

        Returns: (exit_code, stdout, stderr)
        """
        hook_input = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": file_path}
        })

        result = subprocess.run(
            [sys.executable, str(self.validator_path)],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return result.returncode, result.stdout, result.stderr

    def assert_blocked(self, file_path: str, reason_substring: str = ""):
        """Assert that an edit is blocked (exit code 2)."""
        exit_code, stdout, stderr = self.validate_edit(file_path)
        self.assertEqual(exit_code, 2, f"Expected edit to be blocked: {file_path}\nstderr: {stderr}")
        if reason_substring:
            self.assertIn(reason_substring, stderr, f"Expected reason substring '{reason_substring}' in: {stderr}")

    def assert_allowed(self, file_path: str):
        """Assert that an edit is allowed (exit code 0)."""
        exit_code, stdout, stderr = self.validate_edit(file_path)
        self.assertEqual(exit_code, 0, f"Expected edit to be allowed: {file_path}\nstderr: {stderr}")

    # ========================================================================
    # ZERO-ACCESS PATHS (Should be BLOCKED)
    # ========================================================================

    def test_blocks_env_file(self):
        """Block editing .env files."""
        self.assert_blocked(".env", "zero-access path")

    def test_blocks_ssh_keys(self):
        """Block editing SSH keys."""
        self.assert_blocked("~/.ssh/id_rsa", "zero-access path")

    # ========================================================================
    # READ-ONLY PATHS (Should be BLOCKED)
    # ========================================================================

    def test_blocks_package_lock(self):
        """Block editing package-lock.json."""
        self.assert_blocked("package-lock.json", "read-only path")

    def test_blocks_yarn_lock(self):
        """Block editing yarn.lock."""
        self.assert_blocked("yarn.lock", "read-only path")

    def test_blocks_node_modules(self):
        """Block editing files in node_modules."""
        self.assert_blocked("node_modules/package/index.js", "read-only path")

    def test_blocks_dist_folder(self):
        """Block editing files in dist/."""
        self.assert_blocked("dist/bundle.js", "read-only path")

    def test_blocks_venv(self):
        """Block editing files in .venv/."""
        self.assert_blocked(".venv/lib/python3.8/site-packages/pkg/__init__.py", "read-only path")

    def test_blocks_system_files(self):
        """Block editing system files."""
        self.assert_blocked("/etc/hosts", "read-only path")

    # ========================================================================
    # NO-DELETE PATHS (Should be ALLOWED to edit)
    # ========================================================================
    # Note: No-delete paths protect against DELETION, not EDITING.

    def test_allows_editing_readme(self):
        """Allow editing README.md."""
        self.assert_allowed("README.md")

    def test_allows_editing_license(self):
        """Allow editing LICENSE."""
        self.assert_allowed("LICENSE")

    # ========================================================================
    # NORMAL FILES (Should be ALLOWED)
    # ========================================================================

    def test_allows_normal_source_file(self):
        """Allow editing normal source code."""
        self.assert_allowed("src/main.py")
        self.assert_allowed("app/components/Button.tsx")


if __name__ == "__main__":
    unittest.main()
