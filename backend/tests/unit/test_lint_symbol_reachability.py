"""The symbol-reachability gate: what it flags, what it must never flag, its ceiling.

Each case builds a small ``backend/`` tree on disk, because the defects this
kind of check has had were in import resolution, not in the bookkeeping.
"""

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tools.lint import check_symbol_reachability as checker


class FakeBackendTestCase(unittest.TestCase):
    """Builds a throwaway ``backend/`` with the real product package names."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def build(self, files: dict[str, str]) -> None:
        for relative, source in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")

    def findings(self) -> set[tuple[str, str, str]]:
        return {(f.module, f.symbol, f.reason) for f in checker.scan(self.root)}

    def names(self) -> set[str]:
        return {f"{f.module}.{f.symbol}" for f in checker.scan(self.root)}


class TestClasses(FakeBackendTestCase):
    def test_a_symbol_imported_by_another_package_is_live(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/db.py": "def connect() -> None: ...\n",
                "utils/__init__.py": "",
                "utils/job.py": "from shared.db import connect\n",
            }
        )
        self.assertEqual(self.names(), set())

    def test_a_symbol_imported_only_by_tests_is_reported(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/db.py": "def seam() -> None: ...\n",
                "tests/unit/test_db.py": "from shared.db import seam\n",
            }
        )
        self.assertEqual(
            self.findings(), {("shared.db", "seam", "reached only by tests")}
        )

    def test_a_symbol_nobody_imports_is_distinguished(self) -> None:
        self.build(
            {"shared/__init__.py": "", "shared/db.py": "def orphan() -> None: ...\n"}
        )
        self.assertEqual(
            self.findings(),
            {("shared.db", "orphan", "no importer outside its own module")},
        )

    def test_a_symbol_used_only_by_its_own_main_guard_is_live(self) -> None:
        self.build(
            {
                "utils/__init__.py": "",
                "utils/job.py": """
                    def main() -> None: ...

                    if __name__ == "__main__":
                        main()
                    """,
            }
        )
        self.assertEqual(self.names(), set())

    def test_tools_do_not_keep_a_symbol_alive(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/db.py": "def helper() -> None: ...\n",
                "tools/__init__.py": "",
                "tools/report.py": "from shared.db import helper\n",
            }
        )
        self.assertEqual(self.names(), {"shared.db.helper"})


class TestResolution(FakeBackendTestCase):
    def test_a_same_named_local_def_does_not_count(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/db.py": "def connect() -> None: ...\n",
                "utils/__init__.py": "",
                "utils/job.py": """
                    def connect() -> None: ...

                    connect()
                    """,
            }
        )
        self.assertEqual(self.names(), {"shared.db.connect"})

    def test_a_method_call_does_not_revive_a_module_level_name(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/db.py": """
                    def helper() -> None: ...


                    class Other:
                        def helper(self) -> None: ...


                    def caller(other: Other) -> None:
                        other.helper()
                    """,
                "utils/__init__.py": "",
                "utils/job.py": "from shared.db import caller\n",
            }
        )
        self.assertEqual(self.names(), {"shared.db.helper"})

    def test_an_aliased_module_attribute_access_counts(self) -> None:
        self.build(
            {
                "ingest/__init__.py": "",
                "ingest/email/__init__.py": "",
                "ingest/email/email_parser.py": "def sanitize() -> None: ...\n",
                "utils/__init__.py": "",
                "utils/job.py": """
                    import ingest.email.email_parser as ep

                    ep.sanitize()
                    """,
            }
        )
        self.assertEqual(self.names(), set())

    def test_a_dotted_module_attribute_access_counts(self) -> None:
        self.build(
            {
                "ingest/__init__.py": "",
                "ingest/email/__init__.py": "",
                "ingest/email/email_parser.py": "def sanitize() -> None: ...\n",
                "utils/__init__.py": "",
                "utils/job.py": """
                    import ingest.email.email_parser

                    ingest.email.email_parser.sanitize()
                    """,
            }
        )
        self.assertEqual(self.names(), set())

    def test_a_submodule_imported_by_name_then_used_counts(self) -> None:
        self.build(
            {
                "ingest/__init__.py": "",
                "ingest/email/__init__.py": "",
                "ingest/email/email_parser.py": "def sanitize() -> None: ...\n",
                "utils/__init__.py": "",
                "utils/job.py": """
                    from ingest.email import email_parser

                    email_parser.sanitize()
                    """,
            }
        )
        self.assertEqual(self.names(), set())

    def test_a_star_import_is_refused(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/db.py": "def connect() -> None: ...\n",
                "utils/__init__.py": "",
                "utils/job.py": "from shared.db import *\n",
            }
        )
        with self.assertRaisesRegex(ValueError, "star import"):
            checker.scan(self.root)


class TestRelativeImports(FakeBackendTestCase):
    def test_the_anchor_rule(self) -> None:
        self.assertEqual(
            checker._anchor("notifications.email_sender", False, 1), "notifications"
        )
        self.assertEqual(checker._anchor("notifications", True, 1), "notifications")
        self.assertEqual(checker._anchor("ingest.email.parser", False, 2), "ingest")
        self.assertEqual(checker._anchor("ingest.email", True, 2), "ingest")

    def test_a_package_init_relative_import_resolves(self) -> None:
        self.build(
            {
                "notifications/__init__.py": "from .email_sender import send\n",
                "notifications/email_sender.py": "def send() -> None: ...\n",
            }
        )
        self.assertEqual(self.names(), set())

    def test_a_module_relative_import_anchors_at_its_parent(self) -> None:
        self.build(
            {
                "notifications/__init__.py": "",
                "notifications/email_sender.py": "def send() -> None: ...\n",
                "notifications/queue.py": "from .email_sender import send\n",
            }
        )
        self.assertEqual(self.names(), set())

    def test_a_two_level_relative_import_resolves(self) -> None:
        self.build(
            {
                "ingest/__init__.py": "",
                "ingest/common.py": "def used() -> None: ...\n",
                "ingest/email/__init__.py": "",
                "ingest/email/parser.py": "from ..common import used\n",
            }
        )
        self.assertEqual(self.names(), set())


class TestDunderAll(FakeBackendTestCase):
    def test_dunder_all_in_a_package_init_counts(self) -> None:
        self.build(
            {
                "shared/__init__.py": 'def helper() -> None: ...\n\n__all__ = ["helper"]\n'
            }
        )
        self.assertEqual(self.names(), set())

    def test_dunder_all_in_an_ordinary_module_does_not_count(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/errors.py": 'class Oops(ValueError): ...\n\n__all__ = ["Oops"]\n',
            }
        )
        self.assertEqual(self.names(), {"shared.errors.Oops"})

    def test_module_level_dunders_are_never_reported(self) -> None:
        self.build(
            {
                "shared/__init__.py": "",
                "shared/lazy.py": "def __getattr__(name: str) -> object: ...\n",
            }
        )
        self.assertEqual(self.names(), set())


class TestGate(FakeBackendTestCase):
    def test_main_exits_nonzero_over_the_ceiling_and_zero_at_it(self) -> None:
        self.build(
            {"shared/__init__.py": "", "shared/db.py": "def orphan() -> None: ...\n"}
        )
        argv = ["--root", str(self.root)]
        with (
            contextlib.redirect_stderr(io.StringIO()),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with mock.patch.object(checker, "FROZEN_FINDINGS", 0):
                self.assertEqual(checker.main(argv), 1)
            with mock.patch.object(checker, "FROZEN_FINDINGS", 1):
                self.assertEqual(checker.main(argv), 0)


class TestRepository(unittest.TestCase):
    def test_frozen_findings_equal_the_measured_count(self) -> None:
        """Above the count passes the gate but fails here, so the ceiling only goes down."""
        findings = checker.scan(checker.ROOT)
        self.assertEqual(
            len(findings),
            checker.FROZEN_FINDINGS,
            "\n".join(finding.render() for finding in findings),
        )


if __name__ == "__main__":
    unittest.main()
