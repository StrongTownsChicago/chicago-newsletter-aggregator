"""Write the computed analytics as JSON files and print a console summary."""

import json
from pathlib import Path
from typing import Any

SAMPLE_SIZE = 8
LENS_REPORT_TOP_PHRASES = 4


def write_outputs(outputs: dict[str, Any], output_dir: Path) -> dict[str, int]:
    """Write each output as compact JSON; return file sizes in bytes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, int] = {}
    for stem, payload in outputs.items():
        path = output_dir / f"{stem}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        sizes[path.name] = path.stat().st_size
    return sizes


def print_sizes(sizes: dict[str, int], output_dir: Path) -> None:
    """Print where the files went and how big each one is."""
    print(f"\nWrote analytics to {output_dir}")
    for name, size in sizes.items():
        print(f"  {name:<20} {size / 1024:>9.1f} KB")


def print_report(outputs: dict[str, Any]) -> None:
    """Print a few sample results for a quick sanity check."""

    metadata = outputs["metadata"]
    print(
        f"\n{metadata['newsletter_count']} newsletters from {metadata['source_count']} sources, "
        f"{metadata['first_date']} to {metadata['last_date']}; "
        f"{metadata['term_count']} indexed terms (>= {metadata['min_term_newsletters']} newsletters)"
    )

    lenses = outputs["lenses"]
    readable = lenses["readable_newsletters"]
    print(
        f"\nLens hit rates over {readable} newsletters with readable text "
        f"({lenses['text']} text, mentioned at least "
        f"{lenses['min_mentions']} separate times):"
    )
    for lens in lenses["lenses"]:
        top_phrases = ", ".join(
            f"{item['phrase']} ({item['newsletters']})"
            for item in lens["phrases"][:LENS_REPORT_TOP_PHRASES]
        )
        share = lens["newsletters"] / readable if readable else 0
        print(f"  {lens['label']:<34} {share:6.1%}  {top_phrases}")

    rising = outputs["rising"]
    if rising["latest_month"]:
        print(
            f"\nRising terms in {rising['latest_month']} "
            f"({rising['latest_active_wards']} wards active) vs the median of "
            f"{', '.join(rising['baseline_months'])}:"
        )
    for item in rising["terms"][:SAMPLE_SIZE]:
        print(
            f"  {item['term']:<30} {item['latest_wards']:>3} wards "
            f"(baseline {item['baseline_wards']:g}, +{item['ward_gain']:g})"
            f"{' seasonal' if item['seasonal'] else ''}"
        )

    print("\nDistinctive vocabulary (sample wards):")
    for ward, terms in list(outputs["distinctive"]["wards"].items())[:SAMPLE_SIZE]:
        print(
            f"  Ward {ward}: {', '.join(item['term'] for item in terms[:SAMPLE_SIZE])}"
        )
