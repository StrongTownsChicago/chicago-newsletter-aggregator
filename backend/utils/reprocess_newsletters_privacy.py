"""
Reprocess Newsletter Privacy Sanitization

This script allows you to re-apply the latest privacy sanitization rules (patterns and phrase redaction) 
to newsletters already stored in the database.

Usage Examples:
---------------
1.  Dry Run on a single newsletter:
    uv run python utils/reprocess_newsletters_privacy.py <newsletter_uuid>

2.  Commit changes for a single newsletter:
    uv run python utils/reprocess_newsletters_privacy.py <newsletter_uuid> --update

3.  Dry Run on ALL newsletters (minimal output):
    uv run python utils/reprocess_newsletters_privacy.py --all --quiet

4.  Commit changes for ALL newsletters:
    uv run python utils/reprocess_newsletters_privacy.py --all --update --quiet
"""

import os
import argparse
import sys
import difflib
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_supabase_client
from ingest.email.email_parser import sanitize_content

load_dotenv()

def fetch_newsletter(supabase, newsletter_id):
    """Fetch a single newsletter by ID."""
    result = supabase.table("newsletters").select("*").eq("id", newsletter_id).execute()
    return result.data[0] if result.data else None

def fetch_all_newsletters(supabase):
    """Fetch all newsletters from the database."""
    result = supabase.table("newsletters").select("id, subject, source_id, raw_html, plain_text").execute()
    return result.data or []

def show_diff(original, sanitized, label="Content", quiet=False):
    """Print a diff of the changes."""
    if (original or "") == (sanitized or ""):
        if not quiet:
            print(f"  ✓ {label}: No changes needed.")
        return False
    
    if quiet:
        return True

    print(f"\n  ⚠️  {label} Modified:")
    # Calculate diff
    diff = difflib.unified_diff(
        (original or "").splitlines(), 
        (sanitized or "").splitlines(), 
        fromfile='Original', 
        tofile='Sanitized', 
        lineterm=''
    )
    
    # Print only the changed chunks to avoid spam
    diff_lines = list(diff)
    if not diff_lines:
        print("    (Whitespace or trivial changes only)")
        return True

    # Limit output
    for line in diff_lines[:50]:
        if line.startswith('+'):
            print(f"\033[92m{line}\033[0m") # Green
        elif line.startswith('-'):
            print(f"\033[91m{line}\033[0m") # Red
        else:
            print(line)
            
    if len(diff_lines) > 50:
        print(f"    ... and {len(diff_lines) - 50} more lines")
        
    return True

def process_single_newsletter(newsletter, supabase, update=False, quiet=False):
    """Process a single newsletter dict and return True if modified."""
    if not quiet:
        print(f"\n--- Processing '{newsletter.get('subject', 'No Subject')}' ({newsletter['id']}) ---")

    # Sanitize HTML
    original_html = newsletter.get('raw_html') or ""
    sanitized_html = sanitize_content(original_html, 'html', newsletter.get('source_id'))
    html_changed = show_diff(original_html, sanitized_html, "HTML", quiet=quiet)

    # Sanitize Text
    original_text = newsletter.get('plain_text') or ""
    sanitized_text = sanitize_content(original_text, 'text', newsletter.get('source_id'))
    text_changed = show_diff(original_text, sanitized_text, "Plain Text", quiet=quiet)

    modified = html_changed or text_changed

    if modified and update:
        if not quiet:
            print("\n  Updating database...")
        update_data = {
            "raw_html": sanitized_html,
            "plain_text": sanitized_text
        }
        result = supabase.table("newsletters").update(update_data).eq("id", newsletter['id']).execute()
        if result.data:
            if not quiet:
                print("  ✅ Database updated successfully.")
        else:
            if not quiet:
                print("  ❌ Database update failed.")

    return modified

def main():
    parser = argparse.ArgumentParser(description="Reprocess newsletters to apply privacy sanitization.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("newsletter_id", nargs='?', help="UUID of a specific newsletter to process")
    group.add_argument("--all", action="store_true", help="Process all newsletters in the database")
    
    parser.add_argument("--update", action="store_true", help="Commit changes to database")
    parser.add_argument("--quiet", action="store_true", help="Minimal output (best for bulk updates)")
    
    args = parser.parse_args()
    
    print(f"Connecting to database...")
    supabase = get_supabase_client()
    
    if args.all:
        print("Fetching all newsletters...")
        newsletters = fetch_all_newsletters(supabase)
        print(f"Found {len(newsletters)} newsletters to check.")

        count_modified = 0
        for i, newsletter in enumerate(newsletters):
            if not args.quiet:
                print(f"[{i+1}/{len(newsletters)}] ", end="")

            modified = process_single_newsletter(newsletter, supabase, update=args.update, quiet=args.quiet)
            if modified:
                count_modified += 1
                if args.quiet:
                    print(f"Modified: {newsletter['subject']} ({newsletter['id']})")

        print(f"\n--- Summary ---")
        print(f"Total processed: {len(newsletters)}")
        print(f"Modified: {count_modified}")
        if not args.update:
            print("[Dry Run] No changes were saved. Use --update to commit.")

    else:
        print(f"Fetching newsletter {args.newsletter_id}...")
        newsletter = fetch_newsletter(supabase, args.newsletter_id)

        if not newsletter:
            print("❌ Newsletter not found!")
            return

        process_single_newsletter(newsletter, supabase, update=args.update, quiet=args.quiet)

if __name__ == "__main__":
    main()
