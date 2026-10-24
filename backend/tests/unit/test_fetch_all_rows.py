"""shared.db.fetch_all_rows reads every page past the API's row cap."""

import unittest
from types import SimpleNamespace
from typing import Any

from shared.db import fetch_all_rows


class FakeQuery:
    """A query over `rows` that, like PostgREST, returns at most `cap` per range."""

    def __init__(
        self, rows: list[dict[str, Any]], cap: int, ranges: list[tuple[int, int]]
    ):
        self.rows, self.cap, self.ranges = rows, cap, ranges
        self.bounds = (0, len(rows) - 1)

    def range(self, first: int, last: int) -> "FakeQuery":
        self.ranges.append((first, last))
        self.bounds = (first, min(last, first + self.cap - 1))
        return self

    def execute(self) -> SimpleNamespace:
        first, last = self.bounds
        return SimpleNamespace(data=self.rows[first : last + 1])


class TestFetchAllRows(unittest.TestCase):
    def fetch(
        self, row_count: int, **options: int
    ) -> tuple[list[int], list[tuple[int, int]]]:
        rows = [{"id": number} for number in range(row_count)]
        ranges: list[tuple[int, int]] = []
        fetched = fetch_all_rows(lambda: FakeQuery(rows, 3, ranges), **options)
        return [row["id"] for row in fetched], ranges

    def test_reads_every_row_once_in_capped_pages(self) -> None:
        ids, ranges = self.fetch(7, page_size=3)

        self.assertEqual(ids, list(range(7)))
        self.assertEqual(ranges, [(0, 2), (3, 5), (6, 8)])

    def test_a_full_last_page_costs_one_empty_read(self) -> None:
        ids, ranges = self.fetch(6, page_size=3)

        self.assertEqual(ids, list(range(6)))
        self.assertEqual(ranges[-1], (6, 8))

    def test_starts_at_the_offset(self) -> None:
        ids, _ = self.fetch(7, page_size=3, start=2)

        self.assertEqual(ids, list(range(2, 7)))

    def test_stops_at_the_limit_without_an_extra_read(self) -> None:
        ids, ranges = self.fetch(10, page_size=3, start=1, limit=7)

        self.assertEqual(ids, list(range(1, 8)))
        self.assertEqual(ranges, [(1, 3), (4, 6), (7, 7)])

    def test_a_limit_past_the_end_returns_what_exists(self) -> None:
        ids, _ = self.fetch(4, page_size=3, limit=10)

        self.assertEqual(ids, list(range(4)))

    def test_an_empty_result_is_one_read(self) -> None:
        self.assertEqual(self.fetch(0, page_size=3), ([], [(0, 2)]))


if __name__ == "__main__":
    unittest.main()
