"""Read and write the local analytics snapshot directory.

Layout (gitignored, under `backend/data/`):
    newsletters.jsonl.gz  one newsletter per line, gzip-compressed JSON
    sources.json          every source
    metadata.json         format version and the `fetched_through` cursor

`metadata.json` is written last, so an interrupted save leaves the previous
cursor in place and the next refresh simply re-fetches the gap.
"""

import gzip
import json
import os
from datetime import datetime
from pathlib import Path

from analytics.snapshot import (
    Snapshot,
    newsletter_from_row,
    newsletter_to_row,
    source_from_row,
    source_to_row,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = BACKEND_ROOT / "data" / "analytics_snapshot"

SNAPSHOT_FORMAT_VERSION = 1
NEWSLETTERS_FILE = "newsletters.jsonl.gz"
SOURCES_FILE = "sources.json"
METADATA_FILE = "metadata.json"


class SnapshotError(Exception):
    """Raised when a snapshot cannot be used; rebuilding it fixes the problem."""


class SnapshotNotFoundError(SnapshotError):
    """Raised when a snapshot directory is missing or incomplete."""


def load_snapshot(directory: Path) -> Snapshot:
    """Load a snapshot written by `save_snapshot`."""
    paths = [
        directory / name for name in (METADATA_FILE, SOURCES_FILE, NEWSLETTERS_FILE)
    ]
    missing = [path.name for path in paths if not path.exists()]
    if missing:
        raise SnapshotNotFoundError(
            f"Snapshot at {directory} is missing {', '.join(missing)}"
        )

    try:
        return _read_snapshot(directory)
    except SnapshotError:
        raise
    except (OSError, EOFError, ValueError, KeyError, TypeError) as error:
        # Truncated gzip, malformed JSON, or missing fields all mean the same thing.
        raise SnapshotError(
            f"Snapshot at {directory} is unreadable: {error!r}"
        ) from error


def _read_snapshot(directory: Path) -> Snapshot:
    metadata = json.loads((directory / METADATA_FILE).read_text(encoding="utf-8"))
    if metadata.get("format_version") != SNAPSHOT_FORMAT_VERSION:
        raise SnapshotError(
            f"Unsupported snapshot format {metadata.get('format_version')!r} in "
            f"{directory}; expected {SNAPSHOT_FORMAT_VERSION}"
        )
    fetched_through = datetime.fromisoformat(metadata["fetched_through"])
    if fetched_through.tzinfo is None:
        raise SnapshotError(
            f"Snapshot at {directory} has a fetched_through without a timezone"
        )

    sources_rows = json.loads((directory / SOURCES_FILE).read_text(encoding="utf-8"))
    with gzip.open(directory / NEWSLETTERS_FILE, "rt", encoding="utf-8") as file:
        newsletters = [
            newsletter_from_row(json.loads(line)) for line in file if line.strip()
        ]

    return Snapshot(
        sources=[source_from_row(row) for row in sources_rows],
        newsletters=newsletters,
        fetched_through=fetched_through,
    )


def save_snapshot(directory: Path, snapshot: Snapshot, saved_at: datetime) -> None:
    """Write a snapshot, replacing each file only once it is fully written."""
    directory.mkdir(parents=True, exist_ok=True)

    newsletters_temp = directory / f"{NEWSLETTERS_FILE}.tmp"
    with gzip.open(newsletters_temp, "wt", encoding="utf-8") as file:
        for newsletter in snapshot.newsletters:
            file.write(
                json.dumps(newsletter_to_row(newsletter), ensure_ascii=False) + "\n"
            )
    os.replace(newsletters_temp, directory / NEWSLETTERS_FILE)

    _write_json_atomically(
        directory / SOURCES_FILE,
        [source_to_row(source) for source in snapshot.sources],
    )

    received_dates = [newsletter.received_date for newsletter in snapshot.newsletters]
    _write_json_atomically(
        directory / METADATA_FILE,
        {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "fetched_through": snapshot.fetched_through.isoformat(),
            "saved_at": saved_at.isoformat(),
            "newsletter_count": len(snapshot.newsletters),
            "source_count": len(snapshot.sources),
            "received_date_min": min(received_dates).isoformat()
            if received_dates
            else None,
            "received_date_max": max(received_dates).isoformat()
            if received_dates
            else None,
        },
    )


def _write_json_atomically(path: Path, payload: object) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temp_path, path)
