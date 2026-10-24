"""The not-yet-strict test modules only ever shrink, and every entry still binds.

Test modules that cannot yet pass mypy's strict settings are named in
mypy.ini, each with the exact error codes it may break. A list nobody checks
becomes a dumping ground, so every claim is executed: mypy reruns with the
test sections removed, and an entry naming a code its module no longer breaks
fails here. Fixing a module means deleting its entry and lowering the counts.
"""

import configparser
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MYPY_INI = BACKEND / "mypy.ini"

# Every test module is strict. An entry added to mypy.ini fails these counts.
ADOPTED_MODULES = 0
ADOPTED_CODES = 0

TEST_SECTION_PREFIX = "mypy-tests."
# Any other setting (above all ignore_errors) would switch a module off
# without showing up in either count.
PERMITTED_TEST_SETTINGS = frozenset({"disable_error_code"})
PERMITTED_LIBRARY_SETTINGS = frozenset({"ignore_missing_imports"})

ERROR_LINE = re.compile(r"^(?P<path>\S+\.py):\d+: error: .*\[(?P<code>[a-z-]+)\]$")


def read_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(MYPY_INI, encoding="utf-8")
    return parser


def ratchet() -> dict[str, set[str]]:
    """Test module -> the error codes its section disables."""
    config = read_config()
    return {
        section.removeprefix("mypy-"): {
            code.strip()
            for code in config[section].get("disable_error_code", "").split(",")
            if code.strip()
        }
        for section in config.sections()
        if section.startswith(TEST_SECTION_PREFIX)
    }


def module_path(module: str) -> Path:
    return BACKEND.joinpath(*module.split(".")).with_suffix(".py")


def module_name(reported_path: str) -> str:
    relative = Path(reported_path.replace("\\", "/"))
    return ".".join(relative.with_suffix("").parts)


class TestRatchetOnlyShrinks(unittest.TestCase):
    def test_module_count_matches_adoption(self) -> None:
        """Above fails a new entry; below means ADOPTED_MODULES must come down."""
        self.assertEqual(len(ratchet()), ADOPTED_MODULES)

    def test_code_count_matches_adoption(self) -> None:
        """Appending a code to an entry loosens the gate without adding a module."""
        self.assertEqual(sum(len(codes) for codes in ratchet().values()), ADOPTED_CODES)

    def test_every_entry_names_codes(self) -> None:
        empty = sorted(module for module, codes in ratchet().items() if not codes)
        self.assertEqual(empty, [])

    def test_test_sections_carry_only_disable_error_code(self) -> None:
        config = read_config()
        stray = sorted(
            f"[{section}] {key}"
            for section in config.sections()
            if section.startswith(TEST_SECTION_PREFIX)
            for key in config[section]
            if key not in PERMITTED_TEST_SETTINGS
        )
        self.assertEqual(stray, [], "name the codes instead")

    def test_only_test_modules_are_relaxed(self) -> None:
        """Other per-module sections exist only to let a stubless library import."""
        config = read_config()
        stray = sorted(
            f"[{section}] {key}"
            for section in config.sections()
            if section.startswith("mypy-")
            and not section.startswith(TEST_SECTION_PREFIX)
            for key in config[section]
            if key not in PERMITTED_LIBRARY_SETTINGS
        )
        self.assertEqual(stray, [], "product modules stay strict")

    def test_every_entry_names_an_existing_test_module(self) -> None:
        missing = sorted(
            module for module in ratchet() if not module_path(module).is_file()
        )
        self.assertEqual(missing, [], "delete the entries for removed modules")


@unittest.skipIf(importlib.util.find_spec("mypy") is None, "mypy is not installed")
class TestEveryClaimStillFires(unittest.TestCase):
    def strict_errors(self, modules: list[str]) -> dict[str, set[str]]:
        """Run mypy over the modules with every test section removed."""
        config = read_config()
        for section in config.sections():
            if section.startswith(TEST_SECTION_PREFIX):
                config.remove_section(section)
        with tempfile.TemporaryDirectory() as directory:
            strict_ini = Path(directory) / "mypy.ini"
            with strict_ini.open("w", encoding="utf-8") as handle:
                config.write(handle)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mypy",
                    "--config-file",
                    str(strict_ini),
                    "--cache-dir",
                    str(Path(directory) / "cache"),
                    *(
                        str(module_path(module).relative_to(BACKEND))
                        for module in modules
                    ),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=BACKEND,
                check=False,
            )
        found: dict[str, set[str]] = defaultdict(set)
        for line in result.stdout.splitlines():
            match = ERROR_LINE.match(line.strip())
            if match:
                found[module_name(match["path"])].add(match["code"])
        self.assertTrue(
            found,
            f"mypy reported nothing, so nothing was checked:\n{result.stdout}{result.stderr}",
        )
        return found

    def test_every_disabled_code_still_fires(self) -> None:
        claims = ratchet()
        if not claims:
            self.skipTest("no test module is relaxed")
        found = self.strict_errors(sorted(claims))
        stale = {
            module: sorted(codes - found.get(module, set()))
            for module, codes in claims.items()
            if codes - found.get(module, set())
        }
        self.assertEqual(stale, {}, "fixed: delete these codes from mypy.ini")


if __name__ == "__main__":
    unittest.main()
