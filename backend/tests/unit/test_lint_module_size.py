"""The module-size checker: what it counts, its tiers, and the baseline ratchet."""

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

from tools.lint import check_module_size as checker

SOURCE = "analytics/thing.py"

#: Cap name -> the value it was adopted at. Lower freely, never raise.
ADOPTED_CAPS = {"LINE_CAP": 400, "PUBLIC_CAP": 30}


def measure(
    source: str, rel: str = SOURCE, baseline: checker.Baseline | None = None
) -> checker.Metrics:
    return checker.measure(source, rel, baseline or {})


def body(lines: int) -> str:
    """A module of exactly ``lines`` statements, all code and none of it public."""
    return "".join(f"_x{n} = {n}\n" for n in range(lines))


def public_functions(count: int) -> str:
    return "".join(f"def f{n}() -> None: pass\n" for n in range(count))


class TestMeasure(unittest.TestCase):
    def test_blank_lines_are_not_code(self) -> None:
        self.assertEqual(measure("a = 1\n\n\n\nb = 2\n").lines, 2)

    def test_whole_line_comments_are_not_code(self) -> None:
        self.assertEqual(measure("# note\na = 1\n# more\n# and more\n").lines, 1)

    def test_a_trailing_comment_sits_on_a_line_of_code(self) -> None:
        self.assertEqual(measure("a = 1  # why\n").lines, 1)

    def test_docstrings_are_not_code(self) -> None:
        source = (
            '"""Module.\n\nProse.\n"""\n\n\n'
            'def f() -> None:\n    """One.\n\n    Two.\n    """\n'
        )
        self.assertEqual(measure(source).lines, 1)

    def test_a_line_separator_inside_a_string_does_not_shift_lines(self) -> None:
        for separator in ("\x0c", " "):
            with self.subTest(separator=repr(separator)):
                source = f'a = "x{separator}y"\n# note\n# more\nb = 2\n'
                self.assertEqual(measure(source).lines, 2)

    def test_a_string_that_is_not_a_docstring_is_code(self) -> None:
        self.assertEqual(measure('a = 1\n"""not a docstring"""\n').lines, 2)

    def test_public_top_level_symbols_are_counted(self) -> None:
        for source in (
            "def f() -> None: pass\n",
            "class C: pass\n",
            "NAME = 1\n",
            "NAME: int = 1\n",
        ):
            with self.subTest(source=source):
                self.assertEqual(measure(source).public, 1)

    def test_private_and_nested_symbols_are_not_public(self) -> None:
        for source in ("def _f() -> None: pass\n", "class _C: pass\n", "_NAME = 1\n"):
            with self.subTest(source=source):
                self.assertEqual(measure(source).public, 0)
        nested = "def f() -> None:\n    def inner() -> None: pass\n"
        self.assertEqual(measure(nested).public, 1)

    def test_a_declared_all_is_the_public_surface(self) -> None:
        source = '__all__ = ["a", "b", "_c"]\n' + public_functions(5)
        self.assertEqual(measure(source).public, 2)

    def test_a_package_init_counts_its_re_exports(self) -> None:
        source = "from .rule_matcher import match, queue\n"
        self.assertEqual(measure(source, "notifications/__init__.py").public, 2)
        self.assertEqual(measure(source, "notifications/other.py").public, 0)

    def test_an_unreadable_file_is_reported_not_raised(self) -> None:
        metrics = measure("def (\n")
        self.assertTrue(metrics.error)
        self.assertEqual(metrics.violations, ["MS001"])


class TestCapsAndTiers(unittest.TestCase):
    def test_the_line_cap_applies_without_a_baseline_entry(self) -> None:
        self.assertEqual(measure(body(checker.LINE_CAP)).violations, [])
        self.assertEqual(measure(body(checker.LINE_CAP + 1)).violations, ["MS001"])

    def test_the_public_cap_trips_ms003(self) -> None:
        wide = public_functions(checker.PUBLIC_CAP + 1)
        self.assertEqual(measure(wide).violations, ["MS003"])

    def test_test_modules_are_exempt_from_ms003(self) -> None:
        wide = public_functions(checker.PUBLIC_CAP + 1)
        self.assertEqual(measure(wide, "tests/unit/test_thing.py").violations, [])
        self.assertEqual(checker.rules_for("tests/unit/test_thing.py"), {"MS001"})

    def test_a_baseline_entry_raises_the_allowance_to_its_number(self) -> None:
        over = body(checker.LINE_CAP + 50)
        recorded = {SOURCE: {"lines": checker.LINE_CAP + 50}}
        self.assertEqual(measure(over, baseline=recorded).violations, [])
        self.assertEqual(
            measure(over + "_y = 1\n", baseline=recorded).violations, ["MS001"]
        )

    def test_a_baseline_entry_never_lowers_an_allowance_below_the_cap(self) -> None:
        recorded = {SOURCE: {"lines": 900, "public": 2}}
        metrics = measure(public_functions(20), baseline=recorded)
        self.assertEqual(metrics.public, 20)
        self.assertEqual(metrics.violations, [])

    def test_caps_are_at_or_below_their_adopted_values(self) -> None:
        for cap, adopted in ADOPTED_CAPS.items():
            with self.subTest(cap=cap):
                self.assertLessEqual(getattr(checker, cap), adopted)


class TestGrew(unittest.TestCase):
    def test_growth_of_one_file_is_refused(self) -> None:
        growth = checker.grew({SOURCE: {"lines": 410}}, {SOURCE: {"lines": 420}})
        self.assertEqual(len(growth), 2)
        self.assertIn(f"{SOURCE}: lines 420, was 410", growth)

    def test_a_rename_carrying_growth_is_refused_by_the_total(self) -> None:
        growth = checker.grew({"a.py": {"lines": 410}}, {"b.py": {"lines": 600}})
        self.assertEqual(growth, ["total baselined lines 600, was 410"])

    def test_a_new_public_names_entry_is_refused_by_the_total(self) -> None:
        recorded = {"a.py": {"lines": 500}}
        growth = checker.grew(recorded, {**recorded, "b.py": {"public": 45}})
        self.assertEqual(growth, ["total baselined public 45, was 0"])

    def test_shrinking_or_dropping_entries_is_accepted(self) -> None:
        recorded = {"a.py": {"lines": 500}, "b.py": {"lines": 450}}
        self.assertEqual(checker.grew(recorded, {"a.py": {"lines": 480}}), [])

    def test_an_absent_baseline_records_whatever_it_finds(self) -> None:
        self.assertEqual(checker.grew({}, {"a.py": {"lines": 900}}), [])


class TestStaleEntries(unittest.TestCase):
    def test_an_entry_for_a_deleted_file_is_stale(self) -> None:
        measured = [measure(body(10))]
        self.assertEqual(
            checker.stale_entries(measured, {"gone.py": {"lines": 900}}), ["gone.py"]
        )

    def test_an_entry_for_a_file_now_under_the_caps_is_stale(self) -> None:
        measured = [measure(body(10))]
        self.assertEqual(
            checker.stale_entries(measured, {SOURCE: {"lines": 900}}), [SOURCE]
        )

    def test_an_entry_for_a_file_still_over_is_not_stale(self) -> None:
        measured = [measure(body(checker.LINE_CAP + 1))]
        self.assertEqual(
            checker.stale_entries(measured, {SOURCE: {"lines": checker.LINE_CAP + 1}}),
            [],
        )


@contextlib.contextmanager
def sandbox(
    files: dict[str, str], baseline: checker.Baseline | None = None
) -> Iterator[Path]:
    """Point the checker at a throwaway ``backend/`` so ``main`` runs end to end."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for rel, source in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        baseline_path = root / "baseline.json"
        baseline_path.write_text(
            json.dumps({"measured_on": "test", "modules": baseline or {}}),
            encoding="utf-8",
        )
        with (
            mock.patch.object(checker, "ROOT", root),
            mock.patch.object(checker, "BASELINE", baseline_path),
        ):
            yield root


def run_main(argv: list[str]) -> tuple[int, str]:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
        exit_code = checker.main(argv)
    return exit_code, stderr.getvalue()


class TestMain(unittest.TestCase):
    def test_the_gate_fails_and_names_a_file_that_is_too_long(self) -> None:
        with sandbox({"utils/big.py": body(checker.LINE_CAP + 1)}):
            exit_code, stderr = run_main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("utils/big.py: MS001", stderr)

    def test_the_gate_passes_a_small_file(self) -> None:
        with sandbox({"utils/small.py": body(10)}):
            self.assertEqual(run_main([])[0], 0)

    def test_a_baselined_file_passes_until_it_grows(self) -> None:
        over = body(checker.LINE_CAP + 10)
        recorded = {"utils/big.py": {"lines": checker.LINE_CAP + 10}}
        with sandbox({"utils/big.py": over}, recorded) as root:
            self.assertEqual(run_main([])[0], 0)
            (root / "utils" / "big.py").write_text(
                over + "_more = 1\n", encoding="utf-8"
            )
            exit_code, stderr = run_main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("big.py", stderr)

    def test_a_stale_entry_fails_the_gate(self) -> None:
        with sandbox({"utils/small.py": body(10)}, {"utils/small.py": {"lines": 900}}):
            exit_code, stderr = run_main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("no longer needed", stderr)

    def test_update_refuses_to_raise_a_number(self) -> None:
        recorded = {"utils/big.py": {"lines": checker.LINE_CAP + 10}}
        with sandbox({"utils/big.py": body(checker.LINE_CAP + 60)}, recorded):
            exit_code, stderr = run_main(["--update"])
        self.assertEqual(exit_code, 1)
        self.assertIn("only goes down", stderr)

    def test_update_accepts_a_split_that_lowers_the_total(self) -> None:
        files = {"utils/part_a.py": body(300), "utils/part_b.py": body(300)}
        with sandbox(files, {"utils/whole.py": {"lines": 900}}):
            self.assertEqual(run_main(["--update"])[0], 0)
            self.assertEqual(checker.load_baseline(), {})

    def test_a_corrupt_baseline_is_a_named_failure(self) -> None:
        with sandbox({}) as root:
            (root / "baseline.json").write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "unreadable"):
                checker.load_baseline()


class TestShippedBaseline(unittest.TestCase):
    def test_the_repository_passes_its_own_baseline(self) -> None:
        baseline = checker.load_baseline()
        measured = checker.scan_repo(baseline)
        self.assertEqual(checker.gating(measured), [])
        self.assertEqual(checker.stale_entries(measured, baseline), [])

    def test_every_entry_equals_todays_measurement(self) -> None:
        """Raising a number fails here, so the only way down is a smaller file."""
        baseline = checker.load_baseline()
        measured = {m.path: m for m in checker.scan_repo({})}
        rule_for_field = {
            field: rule for rule, (_, field, _cap) in checker.RULES.items()
        }
        self.assertTrue(baseline)
        for path, recorded in baseline.items():
            self.assertIn(path, measured, f"{path} no longer exists")
            for field, value in recorded.items():
                with self.subTest(path=path, field=field):
                    self.assertEqual(
                        value, measured[path].actual(rule_for_field[field])
                    )

    def test_test_entries_record_only_lines(self) -> None:
        for path, recorded in checker.load_baseline().items():
            if path.startswith("tests/"):
                self.assertEqual(set(recorded), {"lines"}, path)

    def test_the_baseline_records_the_tree_it_was_measured_on(self) -> None:
        recorded = json.loads(checker.BASELINE.read_text(encoding="utf-8"))
        self.assertNotEqual(recorded["measured_on"], "unknown")

    def test_the_scan_covers_product_tests_and_tools(self) -> None:
        scanned = {m.path for m in checker.scan_repo({})}
        self.assertIn("notifications/email_sender.py", scanned)
        self.assertTrue(any(p.startswith("tests/") for p in scanned))
        self.assertTrue(any(p.startswith("tools/lint/") for p in scanned))


if __name__ == "__main__":
    unittest.main()
