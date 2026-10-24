"""
Mutation testing for the modules whose tests should be strongest.

cosmic-ray makes small changes to a module (flips a comparison, drops a
condition, swaps an operator) and reruns that module's tests; a mutant the
tests still pass on ("survivor") marks behaviour no test pins down. Dev-only,
not a CI step: each target takes minutes. Sessions are kept in `.mutation/`
(gitignored), so survivors can be listed again without rerunning.

Usage:
    uv run --group mutation python -m tools.run_mutation_tests             # every target
    uv run --group mutation python -m tools.run_mutation_tests rule_matcher
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SESSION_DIRECTORY = BACKEND_ROOT / ".mutation"
# Per test run; a mutant that makes the tests hang (an infinite loop) counts as killed.
TEST_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class MutationTarget:
    module_path: str
    test_modules: tuple[str, ...]


MUTATION_TARGETS = {
    "rule_matcher": MutationTarget(
        "notifications/rule_matcher.py",
        (
            "tests.unit.test_rule_matcher",
            "tests.unit.test_rule_matcher_queue",
            "tests.integration.test_notification_matching",
            "tests.integration.test_empty_digest_flow",
        ),
    ),
    "email_parser": MutationTarget(
        "ingest/email/email_parser.py",
        (
            "tests.unit.test_email_parser",
            "tests.unit.test_email_pattern_properties",
            "tests.unit.test_sanitization",
            "tests.unit.test_sanitization_comprehensive",
            "tests.unit.test_sanitization_link_unwrap",
            "tests.unit.test_sanitization_properties",
            "tests.integration.test_user_cases",
        ),
    ),
    "topic_reach": MutationTarget(
        "analytics/topic_reach.py", ("tests.unit.test_analytics_topic_reach",)
    ),
    "plurals": MutationTarget(
        "analytics/plurals.py",
        (
            "tests.unit.test_analytics_plurals",
            "tests.unit.test_analytics_plurals_properties",
        ),
    ),
    "dates": MutationTarget("shared/dates.py", ("tests.unit.test_dates",)),
}


def build_config(target: MutationTarget) -> str:
    """Return a cosmic-ray TOML config that runs the target's tests with this interpreter.

    The interpreter is named explicitly: a bare `python` can resolve to another
    virtualenv on PATH, whose missing packages would fail every run and make
    every mutant look killed. cosmic-ray splits the command with shlex, so the
    path uses forward slashes.
    """
    test_command = " ".join(
        [f'"{Path(sys.executable).as_posix()}"', "-m unittest -q", *target.test_modules]
    )
    return "\n".join(
        [
            "[cosmic-ray]",
            f'module-path = "{target.module_path}"',
            f"timeout = {TEST_TIMEOUT_SECONDS}.0",
            "excluded-modules = []",
            f"test-command = '{test_command}'",
            "",
            "[cosmic-ray.distributor]",
            'name = "local"',
            "",
        ]
    )


def run_cosmic_ray(*arguments: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "cosmic_ray.cli", *arguments],
        cwd=BACKEND_ROOT,
        check=False,
    ).returncode


def run_target(name: str, target: MutationTarget) -> bool:
    """Mutate one module and report its survivors. False if its tests fail unmutated."""
    config_path = SESSION_DIRECTORY / f"{name}.toml"
    session_path = SESSION_DIRECTORY / f"{name}.sqlite"
    config_path.write_text(build_config(target), encoding="utf-8")
    session_path.unlink(missing_ok=True)

    print(f"\n=== {name}: {target.module_path}", flush=True)
    # Without a passing baseline every mutant counts as killed, so the score would be meaningless.
    if run_cosmic_ray("baseline", str(config_path)) != 0:
        print(f"Baseline failed: the {name} tests fail without any mutation.")
        return False
    run_cosmic_ray("init", str(config_path), str(session_path))
    run_cosmic_ray("exec", str(config_path), str(session_path))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "cosmic_ray.tools.report",
            "--surviving-only",
            "--show-diff",
            str(session_path),
        ],
        cwd=BACKEND_ROOT,
        check=False,
        # Diffs carry the modules' emoji, which a Windows console codepage can't encode.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument(
        "targets",
        nargs="*",
        help=f"Any of: {', '.join(MUTATION_TARGETS)} (default: all)",
    )
    selected = parser.parse_args().targets or list(MUTATION_TARGETS)
    unknown = [name for name in selected if name not in MUTATION_TARGETS]
    if unknown:
        parser.error(f"unknown target(s): {', '.join(unknown)}")

    SESSION_DIRECTORY.mkdir(exist_ok=True)
    failed = [name for name in selected if not run_target(name, MUTATION_TARGETS[name])]
    if failed:
        sys.exit(f"Baseline failed for: {', '.join(failed)}")


if __name__ == "__main__":
    main()
