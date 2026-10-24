"""Privacy reprocessing (cli.reprocess_newsletters_privacy) of stored rows."""

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import cli.reprocess_newsletters_privacy as privacy_cli
from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import sanitize_content
from tests.db_integration.local_supabase import LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source

DIRTY_HTML = (
    "<html><body><p>Leaf pickup starts Monday.</p>"
    '<p><a href="https://example.us1.list-manage.com/unsubscribe?u=1">Unsubscribe</a>'
    "</p></body></html>"
)


class TestReprocessPrivacy(LocalSupabaseTestCase):
    """A row stored before a privacy pattern existed, and a clean one."""

    def setUp(self) -> None:
        self.reset()
        source_id = insert_source(self.db, name="Ward 6 Office", ward_number=6)["id"]
        self.dirty = insert_newsletter(
            self.db,
            source_id,
            raw_html=DIRTY_HTML,
            plain_text="Leaf pickup starts Monday.\nUnsubscribe",
        )["id"]
        clean = sanitize_content(
            "<p>Street sweeping.</p>", "html", PRIVACY_PATTERNS_DICT
        )
        self.clean = insert_newsletter(
            self.db, source_id, raw_html=clean, plain_text="Street sweeping."
        )["id"]

    def run_cli(self, *args: str) -> None:
        with (
            patch("sys.argv", ["reprocess_newsletters_privacy", *args]),
            redirect_stdout(io.StringIO()),
        ):
            privacy_cli.main()

    def row_versions(self) -> dict[str, str]:
        """Each row's xmin: it changes whenever the row is written."""
        return {
            str(row_id): str(xmin)
            for row_id, xmin in self.run_sql("SELECT id, xmin FROM newsletters")
        }

    def assert_dirty_row_sanitized(self, sanitized: bool) -> None:
        (row,) = self.rows("newsletters", id=self.dirty)
        self.assertEqual("list-manage" not in row["raw_html"], sanitized)
        self.assertEqual("Unsubscribe" not in row["plain_text"], sanitized)
        self.assertIn("Leaf pickup starts Monday.", row["plain_text"])

    def test_without_update_nothing_is_written(self) -> None:
        before = self.row_versions()

        self.run_cli(self.dirty)
        self.run_cli("--all")

        self.assertEqual(self.row_versions(), before)
        self.assert_dirty_row_sanitized(False)

    def test_update_rewrites_only_rows_that_change(self) -> None:
        for args in (["{dirty}"], ["--all", "--quiet"]):
            with self.subTest(args=args):
                self.setUp()  # fresh rows, and ids, for each case
                before = self.row_versions()

                self.run_cli(
                    *(arg.format(dirty=self.dirty) for arg in args), "--update"
                )

                self.assert_dirty_row_sanitized(True)
                after = self.row_versions()
                self.assertNotEqual(after[self.dirty], before[self.dirty])
                self.assertEqual(after[self.clean], before[self.clean])
