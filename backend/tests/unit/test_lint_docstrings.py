"""The docstring budget checker: caps, CLI tier, noqa, prose rules, and the DS002 ratchet."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.lint import check_docstrings as checker
from tools.lint import source_trees


def rules_hit(source: str, rel: str = "analytics/thing.py") -> list[str]:
    return [violation.rule for violation in checker.check_source(source, rel)]


def module_docstring(lines: int, *, cli: bool = False) -> str:
    """A module whose docstring spans exactly ``lines`` source lines."""
    body = "".join(f"line {n}\n" for n in range(lines - 2))
    main_guard = 'if __name__ == "__main__":\n    pass\n' if cli else ""
    return f'"""Summary.\n{body}"""\n{main_guard}'


def def_docstring(lines: int) -> str:
    """A ``def`` whose docstring spans exactly ``lines`` source lines."""
    body = "".join(f"    line {n}\n" for n in range(lines - 3))
    return f'def f() -> None:\n    """Summary.\n\n{body}    """\n'


def comment_block(lines: int) -> str:
    return "".join(f"# note {n}\n" for n in range(lines)) + "x = 1\n"


class TestCaps(unittest.TestCase):
    def test_module_docstring_at_the_cap_passes(self) -> None:
        self.assertNotIn("DS001", rules_hit(module_docstring(checker.MODULE_DOC_MAX)))

    def test_module_docstring_over_the_cap_fails(self) -> None:
        self.assertIn("DS001", rules_hit(module_docstring(checker.MODULE_DOC_MAX + 1)))

    def test_cli_entry_module_gets_the_larger_cap(self) -> None:
        at_cap = module_docstring(checker.MODULE_DOC_MAX_CLI, cli=True)
        over_cap = module_docstring(checker.MODULE_DOC_MAX_CLI + 1, cli=True)
        self.assertNotIn("DS001", rules_hit(at_cap))
        self.assertIn("DS001", rules_hit(over_cap))

    def test_a_nested_main_guard_does_not_make_a_cli_module(self) -> None:
        source = module_docstring(checker.MODULE_DOC_MAX + 1) + (
            'def f() -> None:\n    if __name__ == "__main__":\n        pass\n'
        )
        self.assertIn("DS001", rules_hit(source))

    def test_def_docstring_at_the_cap_passes(self) -> None:
        self.assertNotIn("DS002", rules_hit(def_docstring(checker.DEF_DOC_MAX)))

    def test_def_docstring_over_the_cap_fails(self) -> None:
        self.assertIn("DS002", rules_hit(def_docstring(checker.DEF_DOC_MAX + 1)))

    def test_comment_block_at_the_cap_passes(self) -> None:
        self.assertNotIn("DS003", rules_hit(comment_block(checker.COMMENT_BLOCK_MAX)))

    def test_comment_block_over_the_cap_fails(self) -> None:
        self.assertIn("DS003", rules_hit(comment_block(checker.COMMENT_BLOCK_MAX + 1)))

    def test_a_blank_line_ends_a_comment_block(self) -> None:
        half = "".join(f"# note {n}\n" for n in range(checker.COMMENT_BLOCK_MAX))
        self.assertNotIn("DS003", rules_hit(f"{half}\n{half}x = 1\n"))

    def test_a_line_separator_inside_a_string_does_not_shift_lines(self) -> None:
        for separator in ("\x0c", " "):
            with self.subTest(separator=repr(separator)):
                source = f'a = "x{separator}y"\n' + comment_block(
                    checker.COMMENT_BLOCK_MAX + 1
                )
                self.assertIn("DS003", rules_hit(source))

    def test_trailing_comments_do_not_form_a_block(self) -> None:
        source = "".join(f"x{n} = 1  # note {n}\n" for n in range(9))
        self.assertNotIn("DS003", rules_hit(source))

    def test_tests_are_held_to_the_same_caps(self) -> None:
        source = def_docstring(checker.DEF_DOC_MAX + 1)
        self.assertIn("DS002", rules_hit(source, "tests/unit/test_thing.py"))


class TestNoqa(unittest.TestCase):
    def test_noqa_on_the_def_line_suppresses_the_named_code(self) -> None:
        source = def_docstring(checker.DEF_DOC_MAX + 1).replace(
            "def f() -> None:", "def f() -> None:  # noqa: DS002"
        )
        self.assertNotIn("DS002", rules_hit(source))

    def test_noqa_suppresses_only_the_named_code(self) -> None:
        planning_dir = "feature_planning"
        source = (
            "def f() -> None:  # noqa: DS002\n"
            f'    """Do it, per {planning_dir}/notes."""\n'
        )
        self.assertEqual(rules_hit(source), ["DS101"])

    def test_noqa_above_a_module_docstring_suppresses_ds001(self) -> None:
        source = "# noqa: DS001  usage docs\n" + module_docstring(
            checker.MODULE_DOC_MAX + 5
        )
        self.assertNotIn("DS001", rules_hit(source))

    def test_noqa_on_a_comment_line_inside_a_block_suppresses_that_line(self) -> None:
        citation = "feature_planning" + "/x.md"
        source = (
            "# one\n"
            f"# see {citation}  # noqa: DS101  kept for history\n"
            f"# see {citation}\n"
            "x = 1\n"
        )
        violations = checker.check_source(source, "a.py")
        self.assertEqual([(v.rule, v.line) for v in violations], [("DS101", 3)])

    def test_noqa_on_a_comment_block_suppresses_ds003(self) -> None:
        source = "# noqa: DS003  a table\n" + comment_block(checker.COMMENT_BLOCK_MAX)
        self.assertNotIn("DS003", rules_hit(source))


class TestProseRules(unittest.TestCase):
    def test_planning_doc_citations_fail(self) -> None:
        for citation in (
            "feature_planning" + "/plan.md",
            "handoff_archive" + "/x.md",
            "STATIC_CHECKS_" + "HANDOFF.md",
            "docs/" + "plans/x.md",
        ):
            with self.subTest(citation=citation):
                source = f'def f() -> None:\n    """See {citation}."""\n'
                self.assertIn("DS101", rules_hit(source))
                self.assertTrue(checker.gating(checker.check_source(source, "a.py")))

    def test_a_citation_in_a_comment_fails(self) -> None:
        source = "# see " + "feature_planning" + "/x.md\nx = 1\n"
        self.assertEqual(rules_hit(source), ["DS101"])

    def test_a_date_is_reported_but_advisory(self) -> None:
        source = 'def f() -> None:\n    """Use --since 2026-09-01."""\n'
        violations = checker.check_source(source, "utils/thing.py")
        self.assertEqual([v.rule for v in violations], ["DS102"])
        self.assertEqual(checker.gating(violations), [])

    def test_superseded_narrative_is_advisory(self) -> None:
        source = 'def f() -> None:\n    """The ratio approach was refuted."""\n'
        violations = checker.check_source(source, "utils/thing.py")
        self.assertEqual([v.rule for v in violations], ["DS106"])
        self.assertEqual(checker.gating(violations), [])

    def test_unparseable_source_is_reported_not_raised(self) -> None:
        self.assertEqual(rules_hit("def f(\n"), ["DS001"])


class TestRatchet(unittest.TestCase):
    def test_ds002_is_ratcheted_not_gated_per_site(self) -> None:
        violations = checker.check_source(def_docstring(20), "utils/thing.py")
        self.assertEqual(checker.gating(violations), [])
        self.assertEqual(checker.ratchet_counts(violations), {"DS002": 1})

    def test_a_count_over_the_frozen_number_fails(self) -> None:
        violations = checker.check_source(def_docstring(20), "utils/thing.py")
        with mock.patch.dict(checker.FROZEN, {"DS002": 0}):
            self.assertEqual(len(checker.ratchet_failures(violations)), 1)
        with mock.patch.dict(checker.FROZEN, {"DS002": 1}):
            self.assertEqual(checker.ratchet_failures(violations), [])


class TestRepository(unittest.TestCase):
    def test_the_repository_passes_the_gate(self) -> None:
        violations = checker.scan_repo()
        self.assertEqual(checker.gating(violations), [])
        self.assertEqual(checker.ratchet_failures(violations), [])

    def test_frozen_numbers_equal_the_measured_counts(self) -> None:
        """Lower than measured fails the gate; higher fails here, so FROZEN only goes down."""
        self.assertEqual(checker.ratchet_counts(checker.scan_repo()), checker.FROZEN)

    def test_the_scan_covers_product_tests_and_tools(self) -> None:
        scanned = {
            path.relative_to(checker.ROOT).parts[0]
            for path in source_trees.python_files(checker.ROOT)
        }
        self.assertTrue({"analytics", "utils", "tests", "tools"} <= scanned)

    def test_main_fails_and_names_the_site(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "utils").mkdir()
            (root / "utils" / "long.py").write_text(
                module_docstring(checker.MODULE_DOC_MAX + 1), encoding="utf-8"
            )
            stderr = io.StringIO()
            with (
                mock.patch.object(checker, "ROOT", root),
                contextlib.redirect_stderr(stderr),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exit_code = checker.main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("utils/long.py:1: DS001", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
