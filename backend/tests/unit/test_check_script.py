"""scripts/check.sh and Backend CI both run every tools.lint gate, gating."""

import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

RUNNERS = {
    "scripts/check.sh": REPO / "scripts" / "check.sh",
    "backend_tests.yml": REPO / ".github" / "workflows" / "backend_tests.yml",
}


def lint_gate_modules() -> list[str]:
    """The module path of every ``tools/lint/check_*.py`` gate."""
    return [
        f"tools.lint.{path.stem}"
        for path in sorted((BACKEND / "tools" / "lint").glob("check_*.py"))
    ]


class LintGateRunnersTest(unittest.TestCase):
    def test_gates_are_discovered(self) -> None:
        self.assertIn("tools.lint.check_docstrings", lint_gate_modules())

    def test_every_runner_runs_every_gate(self) -> None:
        for runner, path in RUNNERS.items():
            text = path.read_text(encoding="utf-8")
            for module in lint_gate_modules():
                with self.subTest(runner=runner, gate=module):
                    self.assertIn(f"python -m {module}", text)

    def test_no_runner_uses_report_mode(self) -> None:
        # --report lists sites and exits 0, so it never fails a build.
        for runner, path in RUNNERS.items():
            with self.subTest(runner=runner):
                self.assertNotIn("--report", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
