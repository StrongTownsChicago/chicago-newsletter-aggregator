import os
from collections.abc import Callable
from typing import Any, cast

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def get_supabase_client() -> Client:
    """Get initialized Supabase client."""
    url: str | None = os.getenv("SUPABASE_URL")
    key: str | None = os.getenv("SUPABASE_SERVICE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

    return create_client(url, key)


#: PostgREST's max_rows: one response never holds more rows than this.
API_ROW_CAP = 1000


def fetch_all_rows(
    build_query: Callable[[], Any],
    start: int = 0,
    limit: int | None = None,
    page_size: int = API_ROW_CAP,
) -> list[dict[str, Any]]:
    """Rows a query matches from offset `start` (at most `limit`), read in pages past the row cap.

    `build_query` returns a fresh query with a total order (end it on a unique
    column), so pages neither overlap nor skip rows. `page_size` must not
    exceed the cap, or a capped page would look like the last one.
    """
    rows: list[dict[str, Any]] = []
    while limit is None or len(rows) < limit:
        offset = start + len(rows)
        wanted = page_size if limit is None else min(page_size, limit - len(rows))
        page = cast(
            list[dict[str, Any]],
            build_query().range(offset, offset + wanted - 1).execute().data,
        )
        rows.extend(page)
        if len(page) < wanted:
            break
    return rows
