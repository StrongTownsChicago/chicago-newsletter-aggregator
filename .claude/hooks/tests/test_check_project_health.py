import unittest
from unittest.mock import patch, MagicMock
import json
import os
import importlib.util
from io import StringIO

# Helper to import the hook script
def import_hook():
    hook_path = os.path.join(os.getcwd(), ".claude", "hooks", "check-project-health.py")
    spec = importlib.util.spec_from_file_location(
        "check_project_health", 
        hook_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class TestCheckProjectHealth(unittest.TestCase):
    def setUp(self):
        self.hook = import_hook()

    def _mock_git_and_checks(self, mock_run, changed_files, failing_check=None):
        """Helper to mock git diff and subprocess checks."""
        def side_effect(*args, **kwargs):
            mock_process = MagicMock()
            cmd = args[0]

            # Handle git diff command
            if isinstance(cmd, list) and 'git' in cmd:
                mock_process.returncode = 0
                mock_process.stdout = '\n'.join(changed_files)
                mock_process.stderr = ""
                return mock_process

            # Handle check commands
            cmd_str = str(cmd) if isinstance(cmd, str) else ' '.join(cmd)

            if failing_check and failing_check in cmd_str:
                mock_process.returncode = 1
                mock_process.stdout = f"{failing_check} error"
                mock_process.stderr = ""
            else:
                mock_process.returncode = 0
                mock_process.stdout = ""
                mock_process.stderr = ""
            return mock_process

        mock_run.side_effect = side_effect

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_all_pass(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = ['backend/test.py', 'frontend/test.js']
        self._mock_git_and_checks(mock_run, changed_files)

        # Act
        self.hook.main()

        # Assert
        output = json.loads(mock_stdout.getvalue())
        # When checks pass, hook returns empty object (no decision field)
        self.assertNotIn('decision', output)

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_backend_fail(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = ['backend/main.py']
        self._mock_git_and_checks(mock_run, changed_files, failing_check='ruff')

        # Act
        self.hook.main()

        # Assert
        output_str = mock_stdout.getvalue()
        try:
            output = json.loads(output_str)
        except json.JSONDecodeError:
            self.fail(f"Invalid JSON: {output_str}")

        self.assertEqual(output['decision'], 'block')
        self.assertIn("Backend Lint (Ruff) failed", output['reason'])
        self.assertIn("ruff error", output['reason'])

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_frontend_fail(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = ['frontend/src/app.js']
        self._mock_git_and_checks(mock_run, changed_files, failing_check='npm run test')

        # Act
        self.hook.main()

        # Assert
        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output['decision'], 'block')
        self.assertIn("Frontend Tests failed", output['reason'])

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_playwright_fail(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = ['frontend/e2e/test.spec.js']
        self._mock_git_and_checks(mock_run, changed_files, failing_check='test:e2e')

        # Act
        self.hook.main()

        # Assert
        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output['decision'], 'block')
        self.assertIn("Frontend E2E Tests (Playwright) failed", output['reason'])
        self.assertIn("test:e2e error", output['reason'])

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_only_backend_changed(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = ['backend/main.py', 'backend/utils.py']
        self._mock_git_and_checks(mock_run, changed_files)

        # Act
        self.hook.main()

        # Assert - should only run backend checks (3 commands: ruff, mypy, tests)
        # Git diff + 3 backend checks = 4 total calls
        backend_calls = [call for call in mock_run.call_args_list
                        if 'ruff' in str(call) or 'mypy' in str(call) or 'unittest' in str(call)]
        frontend_calls = [call for call in mock_run.call_args_list
                         if 'npm' in str(call)]

        self.assertEqual(len(backend_calls), 3, "Should run 3 backend checks")
        self.assertEqual(len(frontend_calls), 0, "Should not run frontend checks")

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_only_frontend_changed(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = ['frontend/src/app.js', 'frontend/package.json']
        self._mock_git_and_checks(mock_run, changed_files)

        # Act
        self.hook.main()

        # Assert - should only run frontend checks
        backend_calls = [call for call in mock_run.call_args_list
                        if 'ruff' in str(call) or 'mypy' in str(call) or 'unittest' in str(call)]
        frontend_calls = [call for call in mock_run.call_args_list
                         if 'npm' in str(call)]

        self.assertEqual(len(backend_calls), 0, "Should not run backend checks")
        self.assertEqual(len(frontend_calls), 3, "Should run 3 frontend checks")

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_no_changes_skips_all_checks(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        changed_files = []  # No changes
        self._mock_git_and_checks(mock_run, changed_files)

        # Act
        self.hook.main()

        # Assert - should skip all checks when no files changed
        backend_calls = [call for call in mock_run.call_args_list
                        if 'ruff' in str(call) or 'mypy' in str(call) or 'unittest' in str(call)]
        frontend_calls = [call for call in mock_run.call_args_list
                         if 'npm' in str(call)]

        self.assertEqual(len(backend_calls), 0, "Should not run backend checks")
        self.assertEqual(len(frontend_calls), 0, "Should not run frontend checks")

        # Should still return success (empty object)
        output = json.loads(mock_stdout.getvalue())
        self.assertNotIn('decision', output)

if __name__ == '__main__':
    unittest.main()
