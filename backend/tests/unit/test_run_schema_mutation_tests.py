"""Unit tests for tools/run_schema_mutation_tests.py."""

import unittest

from tools.run_schema_mutation_tests import (
    DATABASE_TESTS,
    SCHEMA_TEST_MODULES,
    database_test_modules,
)


class TestDatabaseTestModules(unittest.TestCase):
    def test_runs_every_database_test_module_once_schema_tests_first(self) -> None:
        modules = database_test_modules()

        names = [module.removeprefix("tests.db_integration.") for module in modules]
        self.assertEqual(tuple(names[: len(SCHEMA_TEST_MODULES)]), SCHEMA_TEST_MODULES)
        self.assertCountEqual(
            names, [path.stem for path in DATABASE_TESTS.glob("test_*.py")]
        )


if __name__ == "__main__":
    unittest.main()
