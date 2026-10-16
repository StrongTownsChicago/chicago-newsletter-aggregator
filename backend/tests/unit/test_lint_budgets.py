"""The ruff size ceilings only ever go down, and each one still fires.

Each ceiling in pyproject.toml sits at today's worst function. ADOPTED records
those values: lowering a ceiling means lowering it here too, and raising one
fails. Reading the config is not enough on its own (a rule can be configured
and still be switched off by `ignore` or a per-file ignore), so the last tests
run ruff and check the codes come back.
"""

import importlib.util
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]

# Ceiling name -> the value it was adopted at. Lower freely, never raise.
ADOPTED = {
    "max-complexity": 21,
    "max-args": 8,
    "max-returns": 9,
    "max-branches": 21,
    "max-statements": 65,
}

# Ceiling name -> (ruff table, the rule it configures).
CEILINGS = {
    "max-complexity": ("mccabe", "C901"),
    "max-args": ("pylint", "PLR0913"),
    "max-returns": ("pylint", "PLR0911"),
    "max-branches": ("pylint", "PLR0912"),
    "max-statements": ("pylint", "PLR0915"),
}

SIZE_CODES = frozenset(code for _, code in CEILINGS.values())

# Paths allowed to switch a size rule off: test factories and three one-shot
# maintenance scripts. Adding a path here is a loosening a reviewer should see.
EXEMPT_PATHS = frozenset(
    {
        "tests/*",
        "utils/calculate_token_costs.py",
        "utils/migrate_topics.py",
        "utils/cost_report_generator.py",
    }
)

# Well over every ceiling at once: 13 arguments, 26 returns, 25 branches,
# 151 statements, complexity 26.
PROBE_ARGS = ", ".join(f"a{index}" for index in range(12))
OVERSIZED = (
    f"def oversized(n, {PROBE_ARGS}):\n"
    + "".join(
        f"    if n == {i}:\n"
        + "".join(f"        v{part} = {i}\n" for part in range(4))
        + f"        return v0 + v1 + v2 + v3 + {i}\n"
        for i in range(25)
    )
    + f"    return [{PROBE_ARGS}]\n"
)

# Linted as if it lived in a product package, so product per-file ignores apply.
PROBE_PATH = "shared/_ceiling_probe.py"


def lint_config() -> dict[str, Any]:
    with (BACKEND / "pyproject.toml").open("rb") as handle:
        config: dict[str, Any] = tomllib.load(handle)["tool"]["ruff"]["lint"]
    return config


def run_ruff(*args: str, source: str | None = None) -> set[str]:
    """Run ruff from backend/ and return the codes it reported."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "concise",
            *args,
        ],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=BACKEND,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(f"ruff could not run:\n{result.stderr}")
    return {
        line.split(": ")[1].split(" ")[0]
        for line in result.stdout.splitlines()
        if ": " in line
    }


class TestCeilingsOnlyGoDown(unittest.TestCase):
    def test_each_ceiling_matches_its_adopted_value(self) -> None:
        """Raising a ceiling fails; lowering one means lowering ADOPTED with it."""
        config = lint_config()
        for ceiling, (table, _) in CEILINGS.items():
            with self.subTest(ceiling=ceiling):
                self.assertIn(
                    ceiling,
                    config.get(table, {}),
                    "deleting the ceiling falls back to ruff's default",
                )
                self.assertEqual(config[table][ceiling], ADOPTED[ceiling])

    def test_each_size_rule_is_selected_and_not_ignored(self) -> None:
        config = lint_config()
        for code in sorted(SIZE_CODES):
            with self.subTest(code=code):
                self.assertIn(code, config["select"])
                self.assertNotIn(code, config.get("ignore", []))

    def test_only_the_exempt_paths_switch_a_size_rule_off(self) -> None:
        offending = sorted(
            f"{path}: {sorted(SIZE_CODES & set(codes))}"
            for path, codes in lint_config().get("per-file-ignores", {}).items()
            if SIZE_CODES & set(codes) and path not in EXEMPT_PATHS
        )
        self.assertEqual(offending, [], "raise nothing; split the function instead")


@unittest.skipIf(importlib.util.find_spec("ruff") is None, "ruff is not installed")
class TestCeilingsStillFire(unittest.TestCase):
    def test_ruff_as_configured_reports_every_size_code(self) -> None:
        reported = run_ruff("--stdin-filename", PROBE_PATH, "-", source=OVERSIZED)
        self.assertLessEqual(SIZE_CODES, reported, f"reported: {sorted(reported)}")

    def test_each_ceiling_has_no_slack(self) -> None:
        """One below the ceiling, the function it rests on must be reported."""
        config = lint_config()
        for ceiling, (table, code) in CEILINGS.items():
            with self.subTest(ceiling=ceiling):
                lowered = config[table][ceiling] - 1
                reported = run_ruff(
                    ".",
                    "--select",
                    code,
                    "--config",
                    f"lint.{table}.{ceiling}={lowered}",
                )
                self.assertIn(
                    code,
                    reported,
                    f"nothing needs {ceiling} = {lowered + 1}: lower it here and in ADOPTED",
                )


if __name__ == "__main__":
    unittest.main()
