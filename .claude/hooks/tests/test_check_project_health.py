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

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_all_pass(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True # backend and frontend exist
        
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ""
        mock_process.stderr = ""
        mock_run.return_value = mock_process
        
        # Act
        self.hook.main()
        
        # Assert
        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output['decision'], 'allow')

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_backend_fail(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        
        def side_effect(*args, **kwargs):
            mock_process = MagicMock()
            cmd = args[0]
            if isinstance(cmd, list):
                cmd = " ".join(cmd)
            
            # Note: The hook uses shell=True on Windows, so cmd might be string or list
            # We need to check both or check contents
            cmd_str = str(cmd)
            
            if "ruff" in cmd_str:
                mock_process.returncode = 1
                mock_process.stdout = "Lint error"
                mock_process.stderr = ""
            else:
                mock_process.returncode = 0
                mock_process.stdout = ""
                mock_process.stderr = ""
            return mock_process

        mock_run.side_effect = side_effect
        
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
        self.assertIn("Lint error", output['reason'])

    @patch('subprocess.run')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('os.path.exists')
    def test_frontend_fail(self, mock_exists, mock_stdout, mock_run):
        # Arrange
        mock_exists.return_value = True
        
        def side_effect(*args, **kwargs):
            mock_process = MagicMock()
            cmd = args[0]
            cmd_str = str(cmd)
            
            if "npm run test" in cmd_str:
                mock_process.returncode = 1
                mock_process.stdout = "Test failed"
                mock_process.stderr = ""
            else:
                mock_process.returncode = 0
                mock_process.stdout = ""
                mock_process.stderr = ""
            return mock_process

        mock_run.side_effect = side_effect
        
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
        
        def side_effect(*args, **kwargs):
            mock_process = MagicMock()
            cmd_str = str(args[0])
            
            if "test:e2e" in cmd_str:
                mock_process.returncode = 1
                mock_process.stdout = "Playwright failure"
                mock_process.stderr = ""
            else:
                mock_process.returncode = 0
                mock_process.stdout = ""
                mock_process.stderr = ""
            return mock_process

        mock_run.side_effect = side_effect
        
        # Act
        self.hook.main()
        
        # Assert
        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output['decision'], 'block')
        self.assertIn("Frontend E2E Tests (Playwright) failed", output['reason'])
        self.assertIn("Playwright failure", output['reason'])

if __name__ == '__main__':
    unittest.main()
