import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from shared.db import get_supabase_client

MAX_SAMPLES_PER_SOURCE = 1
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../samples")


def download_samples() -> None:
    """Download recent newsletters from each source for privacy pattern analysis"""
    supabase = get_supabase_client()

    # ensure output directory exists
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now()}] Starting sample download to {OUTPUT_DIR}...")

    # Get all sources
    result = supabase.table("sources").select("id, name").execute()
    sources = cast(list[dict[str, Any]], result.data)

    print(f"Found {len(sources)} sources. Fetching samples...")

    count = 0
    for source in sources:
        source_id = cast(int, source["id"])
        source_name = cast(str, source["name"])

        # Get most recent newsletter for this source
        # querying directly for fields we want
        try:
            ns_result = (
                supabase.table("newsletters")
                .select("id, subject, raw_html, plain_text, received_date")
                .eq("source_id", source_id)
                .order("received_date", desc=True)
                .limit(MAX_SAMPLES_PER_SOURCE)
                .execute()
            )

            newsletters = cast(list[dict[str, Any]], ns_result.data)

            if not newsletters:
                print(f"  - {source_name}: No newsletters found")
                continue

            for nl in newsletters:
                # Create a safe filename slug
                safe_name = "".join([c if c.isalnum() else "_" for c in source_name])
                received_date = cast(str | None, nl.get("received_date"))
                date_str = received_date.split("T")[0] if received_date else "unknown"
                base_filename = f"{source_id}_{safe_name}_{date_str}"

                # Save HTML
                raw_html = cast(str | None, nl.get("raw_html"))
                if raw_html:
                    with open(
                        os.path.join(OUTPUT_DIR, f"{base_filename}.html"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(raw_html)

                # Save Plain Text
                plain_text = cast(str | None, nl.get("plain_text"))
                if plain_text:
                    with open(
                        os.path.join(OUTPUT_DIR, f"{base_filename}.txt"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(plain_text)

                subject = cast(str | None, nl.get("subject"))
                subject_preview = subject[:30] if subject else "No Subject"
                print(f"  ✓ {source_name}: Saved sample ({subject_preview}...)")
                count += 1

        except Exception as e:
            print(f"  ✗ {source_name}: Error fetching samples: {e}")

    print(f"\nDownload complete. Saved {count} samples from {len(sources)} sources.")


if __name__ == "__main__":
    download_samples()
