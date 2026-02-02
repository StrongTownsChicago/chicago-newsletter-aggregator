import json
import subprocess
import sys
import os

def run_check(command, cwd, description):
    try:
        # On Windows, shell=True helps with resolving PATH for npm/uv
        use_shell = os.name == 'nt'
        
        # If not using shell, we need to split the command
        args = command.split() if not use_shell else command
        
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=use_shell
        )
        
        if result.returncode != 0:
            # combine stdout and stderr
            output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            return False, f"{description} failed:\n{output.strip()}"
        return True, ""
    except Exception as e:
        return False, f"{description} failed to run: {str(e)}"

def main():
    # Read input (optional, but good practice to clear buffer)
    try:
        if not sys.stdin.isatty():
             _ = sys.stdin.read()
    except Exception:
        pass

    errors = []

    # Backend Checks
    backend_path = "backend"
    if os.path.exists(backend_path):
        checks = [
            ("uv run ruff check .", "Backend Lint (Ruff)"),
            ("uv run mypy .", "Backend Type Check (MyPy)"),
            ("uv run python -m unittest discover -s tests", "Backend Tests")
        ]
        
        for cmd, desc in checks:
            success, msg = run_check(cmd, backend_path, desc)
            if not success:
                errors.append(msg)

    # Frontend Checks
    frontend_path = "frontend"
    if os.path.exists(frontend_path):
        checks = [
            ("npm run lint", "Frontend Lint"),
            ("npm run test", "Frontend Tests"),
            ("npm run test:e2e -- --project=chromium", "Frontend E2E Tests (Playwright)")
        ]
        
        for cmd, desc in checks:
             success, msg = run_check(cmd, frontend_path, desc)
             if not success:
                 errors.append(msg)

    if errors:
        # Truncate if too long to avoid overwhelming context
        full_error = "\n\n".join(errors)
        if len(full_error) > 8000:
            full_error = full_error[:8000] + "\n... (truncated)"
            
        print(json.dumps({
            "decision": "block",
            "reason": f"Project health checks failed:\n{full_error}"
        }))
    else:
        # For Stop hooks, omit the decision field to allow stopping
        print(json.dumps({}))

if __name__ == "__main__":
    main()
