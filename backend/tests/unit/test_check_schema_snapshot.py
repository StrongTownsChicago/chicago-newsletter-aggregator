"""tools/check_schema_snapshot.py: migrations vs. the production snapshot."""

import unittest

from tools.check_schema_snapshot import (
    PENDING_IN_PRODUCTION,
    schema_lines,
    unexpected_differences,
)

SNAPSHOT = """-- header comment
CREATE TABLE "public"."sources" ("id" integer);

    INSERT INTO public.user_profiles (id, email)  -- dashboard comment
CREATE POLICY "Allow public read access" ON "public"."email_source_mappings" FOR SELECT USING (true);
"""

MIGRATED = """-- another header
CREATE TABLE "public"."sources" ("id" integer);
    INSERT INTO public.user_profiles (id, email)
"""


class TestSchemaLines(unittest.TestCase):
    def test_drops_comments_and_blank_lines(self) -> None:
        self.assertEqual(
            schema_lines("-- a\n\nSELECT 1;  -- trailing\n  \nSELECT 1;\n"),
            {"SELECT 1;": 2},
        )


class TestUnexpectedDifferences(unittest.TestCase):
    def test_pending_migration_lines_are_not_differences(self) -> None:
        self.assertIn("006_enable_rls_public_tables.sql", PENDING_IN_PRODUCTION)
        self.assertEqual(unexpected_differences(SNAPSHOT, MIGRATED), ([], []))

    def test_reports_lines_on_either_side(self) -> None:
        migrated = MIGRATED.replace('("id" integer)', '("id" bigint)')
        self.assertEqual(
            unexpected_differences(SNAPSHOT, migrated),
            (
                ['CREATE TABLE "public"."sources" ("id" integer);'],
                ['CREATE TABLE "public"."sources" ("id" bigint);'],
            ),
        )

    def test_a_dropped_duplicate_line_is_a_difference(self) -> None:
        snapshot = "GRANT ALL ON x TO anon;\nGRANT ALL ON x TO anon;\n"
        self.assertEqual(
            unexpected_differences(snapshot, "GRANT ALL ON x TO anon;\n"),
            (["GRANT ALL ON x TO anon;"], []),
        )


if __name__ == "__main__":
    unittest.main()
