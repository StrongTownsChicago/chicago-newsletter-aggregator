
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

def show_diff(original, sanitized, label="Content"):
    """Print a diff of the changes."""
    if original == sanitized:
        print(f"  ✓ {label}: No changes needed.")
        return False
    
    print(f"\n  ⚠️  {label} Modified:")
    # Calculate diff
    diff = difflib.unified_diff(
        original.splitlines(), 
        sanitized.splitlines(), 
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

def main():
    parser = argparse.ArgumentParser(description="Reprocess a newsletter to apply privacy sanitization.")
    parser.add_argument("newsletter_id", help="UUID of the newsletter to process")
    parser.add_argument("--update", action="store_true", help="Commit changes to database")
    
    args = parser.parse_args()
    
    print(f"Connecting to database...")
    supabase = get_supabase_client()
    
    print(f"Fetching newsletter {args.newsletter_id}...")
    newsletter = fetch_newsletter(supabase, args.newsletter_id)
    
    if not newsletter:
        print("❌ Newsletter not found!")
        return

    print(f"Processing '{newsletter['subject']}' from source {newsletter['source_id']}...")
    
    # Sanitize HTML
    original_html = newsletter.get('raw_html') or ""
    sanitized_html = sanitize_content(original_html, 'html', newsletter.get('source_id'))
    html_changed = show_diff(original_html, sanitized_html, "HTML")
    
    # Sanitize Text
    original_text = newsletter.get('plain_text') or ""
    sanitized_text = sanitize_content(original_text, 'text', newsletter.get('source_id'))
    text_changed = show_diff(original_text, sanitized_text, "Plain Text")
    
    if not (html_changed or text_changed):
        print("\n✅ Newsletter is already clean.")
        return

    if args.update:
        print("\nUpdating database...")
        update_data = {
            "raw_html": sanitized_html,
            "plain_text": sanitized_text
        }
        result = supabase.table("newsletters").update(update_data).eq("id", newsletter['id']).execute()
        if result.data:
            print("✅ Database updated successfully.")
        else:
            print("❌ Database update failed.")
    else:
        print("\n[Dry Run] No changes saved. Use --update to commit.")

if __name__ == "__main__":
    main()
