import json
import subprocess
import sys
import os


def get_changed_files() -> list[str]:
    """Get list of changed files using git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
        )
        if result.returncode == 0:
            return result.stdout.splitlines()
        return []
    except Exception:
        # If git for some reason fails, assume all files changed (run all checks)
        return []


def run_check(command: str, cwd: str, description: str) -> tuple[bool, str]:
    try:
        # On Windows, shell=True helps with resolving PATH for npm/uv
        use_shell = os.name == "nt"

        # If not using shell, we need to split the command
        args = command.split() if not use_shell else command

        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, shell=use_shell
        )

        if result.returncode != 0:
            # combine stdout and stderr
            output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            return False, f"{description} failed:\n{output.strip()}"
        return True, ""
    except Exception as e:
        return False, f"{description} failed to run: {str(e)}"


def main() -> None:
    # Read input (optional, but good practice to clear buffer)
    try:
        if not sys.stdin.isatty():
            _ = sys.stdin.read()
    except Exception:
        pass

    errors = []

    # Get changed files to determine which checks to run
    changed_files = get_changed_files()
    backend_changed = any(f.startswith("backend/") for f in changed_files)
    frontend_changed = any(f.startswith("frontend/") for f in changed_files)

    # Backend Checks
    backend_path = "backend"
    if os.path.exists(backend_path) and backend_changed:
        checks = [
            ("uv run ruff check .", "Backend Lint (Ruff)"),
            ("uv run mypy .", "Backend Type Check (MyPy)"),
            ("uv run python -m unittest discover -s tests", "Backend Tests"),
        ]

        for cmd, desc in checks:
            success, msg = run_check(cmd, backend_path, desc)
            if not success:
                errors.append(msg)

    # Frontend Checks
    frontend_path = "frontend"
    if os.path.exists(frontend_path) and frontend_changed:
        checks = [
            ("npm run lint", "Frontend Lint"),
            ("npm run test", "Frontend Tests"),
            (
                "npm run test:e2e -- --project=chromium",
                "Frontend E2E Tests (Playwright)",
            ),
        ]

        for cmd, desc in checks:
            success, msg = run_check(cmd, frontend_path, desc)
            if not success:
                errors.append(msg)

    if errors:
        # Truncate if too long to avoid overwhelming context
        full_error = "\n\n".join(errors)
        if len(full_error) > 12000:
            full_error = full_error[:12000] + "\n... (truncated)"

        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": f"Project health checks failed:\n{full_error}",
                }
            )
        )
    else:
        # For Stop hooks, omit the decision field to allow stopping
        print(json.dumps({}))


if __name__ == "__main__":
    main()
