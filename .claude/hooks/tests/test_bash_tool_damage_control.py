"""
Tests for bash-tool-damage-control.py

IMPORTANT: These tests validate that the hooks correctly BLOCK dangerous commands.
The dangerous commands are passed as JSON strings to the validator and are NEVER executed.
All tests run the validator in isolation - no actual shell commands are run.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar


class TestBashToolDamageControl(unittest.TestCase):
    """Test bash command safety validation."""

    validator_path: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test fixtures."""
        cls.validator_path = (
            Path(__file__).parent.parent / "bash-tool-damage-control.py"
        )
        if not cls.validator_path.exists():
            raise FileNotFoundError(f"Validator not found: {cls.validator_path}")

    def validate_command(self, command: str) -> tuple[int, str, str]:
        """
        Validate a bash command by passing it to the validator as JSON.
        SAFE: Command is passed as text to validator, never executed.

        Returns: (exit_code, stdout, stderr)
        """
        hook_input = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}}
        )

        result = subprocess.run(
            [sys.executable, str(self.validator_path)],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=5,
        )

        return result.returncode, result.stdout, result.stderr

    def assert_blocked(self, command: str, reason_substring: str = "") -> None:
        """Assert that a command is blocked (exit code 2)."""
        exit_code, stdout, stderr = self.validate_command(command)
        self.assertEqual(
            exit_code, 2, f"Expected command to be blocked: {command}\nstderr: {stderr}"
        )
        if reason_substring:
            self.assertIn(
                reason_substring,
                stderr,
                f"Expected reason substring '{reason_substring}' in: {stderr}",
            )

    def assert_allowed(self, command: str) -> None:
        """Assert that a command is allowed (exit code 0)."""
        exit_code, stdout, stderr = self.validate_command(command)
        self.assertEqual(
            exit_code, 0, f"Expected command to be allowed: {command}\nstderr: {stderr}"
        )

    def assert_asks(self, command: str, reason_substring: str = "") -> None:
        """Assert that a command requires confirmation (exit code 0 with ask decision)."""
        exit_code, stdout, stderr = self.validate_command(command)
        self.assertEqual(
            exit_code, 0, f"Expected command to ask for confirmation: {command}"
        )
        try:
            response = json.loads(stdout)
            self.assertEqual(
                response.get("hookSpecificOutput", {}).get("permissionDecision"), "ask"
            )
            if reason_substring:
                reason = response.get("hookSpecificOutput", {}).get(
                    "permissionDecisionReason", ""
                )
                self.assertIn(reason_substring, reason)
        except json.JSONDecodeError:
            self.fail(f"Expected JSON response with 'ask' decision, got: {stdout}")

    # ========================================================================
    # DESTRUCTIVE FILE OPERATIONS
    # ========================================================================

    def test_blocks_rm_rf_root(self) -> None:
        """Block rm -rf on root directory."""
        self.assert_blocked("rm -rf /", "rm with recursive or force flags")

    def test_blocks_rm_rf_home(self) -> None:
        """Block rm -rf on home directory."""
        self.assert_blocked("rm -rf ~", "rm with recursive or force flags")

    def test_blocks_rm_rf_current(self) -> None:
        """Block rm -rf on current directory."""
        self.assert_blocked("rm -rf .", "rm with recursive or force flags")

    def test_blocks_sudo_rm(self) -> None:
        """Block sudo rm commands."""
        self.assert_blocked("sudo rm file.txt", "sudo rm")

    def test_allows_safe_rm(self) -> None:
        """Allow rm without dangerous flags."""
        self.assert_allowed("rm temp.txt")

    # ========================================================================
    # GIT OPERATIONS
    # ========================================================================

    def test_blocks_git_reset_hard(self) -> None:
        """Block git reset --hard."""
        self.assert_blocked("git reset --hard HEAD~1", "git reset --hard")

    def test_blocks_git_push_force(self) -> None:
        """Block git push --force."""
        self.assert_blocked("git push origin main --force", "git push --force")

    def test_blocks_git_push_f(self) -> None:
        """Block git push -f."""
        self.assert_blocked("git push -f origin main", "git push -f")

    def test_allows_git_push_force_with_lease(self) -> None:
        """Allow git push --force-with-lease (safer alternative)."""
        self.assert_allowed("git push --force-with-lease origin main")

    def test_blocks_git_clean_fd(self) -> None:
        """Block git clean -fd."""
        self.assert_blocked("git clean -fd", "git clean with force/directory flags")

    def test_blocks_git_stash_clear(self) -> None:
        """Block git stash clear."""
        self.assert_blocked("git stash clear", "git stash clear")

    def test_asks_git_checkout_discard(self) -> None:
        """Ask confirmation for git checkout -- . (discards changes)."""
        self.assert_asks("git checkout -- .", "Discards all uncommitted changes")

    def test_asks_git_stash_drop(self) -> None:
        """Ask confirmation for git stash drop."""
        self.assert_asks("git stash drop", "Permanently deletes a stash")

    def test_allows_safe_git_commands(self) -> None:
        """Allow safe git commands."""
        self.assert_allowed("git status")
        self.assert_allowed("git log")
        self.assert_allowed("git diff")
        self.assert_allowed("git add .")
        self.assert_allowed("git commit -m 'test'")

    # ========================================================================
    # CLOUD PLATFORMS
    # ========================================================================

    def test_blocks_aws_s3_rm_recursive(self) -> None:
        """Block AWS S3 recursive delete."""
        self.assert_blocked(
            "aws s3 rm s3://bucket --recursive", "aws s3 rm --recursive"
        )

    def test_blocks_aws_ec2_terminate(self) -> None:
        """Block AWS EC2 instance termination."""
        self.assert_blocked(
            "aws ec2 terminate-instances --instance-ids i-1234",
            "aws ec2 terminate-instances",
        )

    def test_blocks_gcloud_projects_delete(self) -> None:
        """Block GCP project deletion."""
        self.assert_blocked(
            "gcloud projects delete my-project", "gcloud projects delete"
        )

    def test_blocks_terraform_destroy(self) -> None:
        """Block terraform destroy."""
        self.assert_blocked("terraform destroy", "terraform destroy")

    def test_blocks_docker_system_prune_all(self) -> None:
        """Block docker system prune -a."""
        self.assert_blocked("docker system prune -a", "docker system prune -a")

    def test_blocks_kubectl_delete_all(self) -> None:
        """Block kubectl delete all."""
        self.assert_blocked("kubectl delete all --all", "kubectl delete all --all")

    # ========================================================================
    # DATABASE OPERATIONS
    # ========================================================================

    def test_blocks_redis_flushall(self) -> None:
        """Block Redis FLUSHALL."""
        self.assert_blocked("redis-cli FLUSHALL", "redis-cli FLUSHALL")

    def test_blocks_mongo_drop_database(self) -> None:
        """Block MongoDB dropDatabase."""
        self.assert_blocked(
            "mongosh --eval 'db.dropDatabase()'", "MongoDB dropDatabase"
        )

    def test_blocks_postgres_dropdb(self) -> None:
        """Block PostgreSQL dropdb."""
        self.assert_blocked("dropdb mydb", "PostgreSQL dropdb")

    # ========================================================================
    # SQL OPERATIONS
    # ========================================================================

    def test_blocks_delete_without_where(self) -> None:
        """Block DELETE without WHERE clause."""
        self.assert_blocked("DELETE FROM users;", "DELETE without WHERE clause")

    def test_blocks_truncate_table(self) -> None:
        """Block TRUNCATE TABLE."""
        self.assert_blocked("TRUNCATE TABLE users", "TRUNCATE TABLE")

    def test_blocks_drop_table(self) -> None:
        """Block DROP TABLE."""
        self.assert_blocked("DROP TABLE users", "DROP TABLE")

    def test_blocks_drop_database(self) -> None:
        """Block DROP DATABASE."""
        self.assert_blocked("DROP DATABASE production", "DROP DATABASE")

    def test_asks_delete_with_where(self) -> None:
        """Ask confirmation for DELETE with specific ID."""
        self.assert_asks(
            "DELETE FROM users WHERE id = 123", "SQL DELETE with specific ID"
        )

    # ========================================================================
    # ZERO-ACCESS PATHS
    # ========================================================================

    def test_blocks_cat_env_file(self) -> None:
        """Block reading .env files."""
        self.assert_blocked("cat .env", "zero-access")

    def test_blocks_cat_backend_env(self) -> None:
        """Block reading backend/.env."""
        self.assert_blocked("cat backend/.env", "zero-access")

    def test_blocks_echo_to_env(self) -> None:
        """Block writing to .env files."""
        self.assert_blocked("echo 'SECRET=foo' > .env", "zero-access")

    # ========================================================================
    # READ-ONLY PATHS
    # ========================================================================

    def test_blocks_modify_package_lock(self) -> None:
        """Block modifying package-lock.json."""
        self.assert_blocked("echo '{}' > package-lock.json", "read-only path")

    def test_blocks_sed_on_lock_file(self) -> None:
        """Block in-place edit of lock file."""
        self.assert_blocked("sed -i 's/foo/bar/' yarn.lock", "read-only path")

    def test_allows_reading_lock_file(self) -> None:
        """Allow reading lock files."""
        self.assert_allowed("cat package-lock.json")

    # ========================================================================
    # NO-DELETE PATHS
    # ========================================================================

    def test_blocks_delete_claude_md(self) -> None:
        """Block deleting CLAUDE.md."""
        self.assert_blocked("rm CLAUDE.md", "no-delete path")

    def test_blocks_delete_readme(self) -> None:
        """Block deleting README.md."""
        self.assert_blocked("rm README.md", "no-delete path")

    def test_allows_editing_readme(self) -> None:
        """Allow editing README.md."""
        self.assert_allowed("nano README.md")

    # ========================================================================
    # SYSTEM-LEVEL OPERATIONS
    # ========================================================================

    def test_blocks_mkfs(self) -> None:
        """Block filesystem format command."""
        self.assert_blocked("mkfs.ext4 /dev/sda1", "filesystem format command")

    def test_blocks_dd_to_device(self) -> None:
        """Block dd writing to device."""
        self.assert_blocked("dd if=/dev/zero of=/dev/sda", "dd writing to device")

    def test_blocks_kill_all_processes(self) -> None:
        """Block kill -9 -1."""
        self.assert_blocked("kill -9 -1", "kill all processes")

    # ========================================================================
    # SAFE COMMANDS
    # ========================================================================

    def test_allows_ls(self) -> None:
        """Allow ls command."""
        self.assert_allowed("ls -la")

    def test_allows_pwd(self) -> None:
        """Allow pwd command."""
        self.assert_allowed("pwd")

    def test_allows_echo(self) -> None:
        """Allow echo to stdout."""
        self.assert_allowed("echo 'hello world'")

    def test_allows_grep(self) -> None:
        """Allow grep command."""
        self.assert_allowed("grep 'pattern' file.txt")

    def test_allows_npm_install(self) -> None:
        """Allow npm install."""
        self.assert_allowed("npm install")

    def test_allows_python_run(self) -> None:
        """Allow running Python scripts."""
        self.assert_allowed("python script.py")


if __name__ == "__main__":
    unittest.main()
