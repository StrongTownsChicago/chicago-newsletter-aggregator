"""Unit tests for tools/run_mutation_tests.py."""

import shlex
import sys
import tomllib
import unittest
from pathlib import Path

from tools.run_mutation_tests import BACKEND_ROOT, MUTATION_TARGETS, build_config


class TestMutationTargets(unittest.TestCase):
    def test_every_target_names_existing_files(self) -> None:
        for name, target in MUTATION_TARGETS.items():
            with self.subTest(target=name):
                self.assertTrue((BACKEND_ROOT / target.module_path).is_file())
                for module in target.test_modules:
                    test_path = BACKEND_ROOT / f"{module.replace('.', '/')}.py"
                    self.assertTrue(test_path.is_file(), test_path)

    def test_config_runs_the_target_tests_with_this_interpreter(self) -> None:
        target = MUTATION_TARGETS["rule_matcher"]

        config = tomllib.loads(build_config(target))["cosmic-ray"]
        command = shlex.split(config["test-command"])

        self.assertEqual(config["module-path"], target.module_path)
        self.assertEqual(Path(command[0]), Path(sys.executable))
        self.assertEqual(command[1:4], ["-m", "unittest", "-q"])
        self.assertEqual(tuple(command[4:]), target.test_modules)


if __name__ == "__main__":
    unittest.main()
