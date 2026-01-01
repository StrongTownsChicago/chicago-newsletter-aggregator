import os
from datetime import datetime
from imap_tools import MailBox, AND, MailMessageFlags
from supabase import create_client
from dotenv import load_dotenv
from email_parser import parse_newsletter

load_dotenv()

# Configuration
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def newsletter_exists(email_uid: str) -> bool:
    """Check if newsletter already processed"""
    result = supabase.table("newsletters").select("id").eq("email_uid", email_uid).execute()
    return len(result.data) > 0

def save_unmapped_report(unmapped_emails):
    """Save unmapped emails to a log file"""
    if not unmapped_emails:
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"unmapped_emails_{timestamp}.txt"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Unmapped Emails Report - {datetime.now()}\n")
        f.write("=" * 60 + "\n\n")
        
        for i, email in enumerate(unmapped_emails, 1):
            f.write(f"{i}. From: {email['from']}\n")
            f.write(f"   Subject: {email['subject']}\n")
            f.write(f"   Date: {email['date']}\n\n")
    
    print(f"\n  Report saved to: {filename}")

def process_new_newsletters():
    """Main processing function"""
    
    print(f"[{datetime.now()}] Starting newsletter ingestion...")
    
    # Connect to Gmail
    with MailBox('imap.gmail.com').login(GMAIL_ADDRESS, GMAIL_PASSWORD) as mailbox:
        
        # Fetch unread emails
        messages = mailbox.fetch(AND(seen=False))
        # Below line can be uncommented to process all emails for testing
        # messages = mailbox.fetch()
        
        processed_count = 0
        skipped_count = 0
        unmapped_count = 0
        unmapped_emails = []  # Track unmapped emails for summary
        
        for msg in messages:
            try:
                # Skip if already processed
                if newsletter_exists(msg.uid):
                    print(f"⊘ Duplicate: {msg.subject[:50]}...")
                    skipped_count += 1
                    continue
                
                # Parse email
                print(f"Processing: {msg.subject}")
                newsletter = parse_newsletter(msg, supabase)
                
                # Check if source was matched
                if newsletter['source_id'] is None:
                    unmapped_count += 1
                    unmapped_info = {
                        'from': msg.from_,
                        'subject': msg.subject,
                        'date': msg.date.isoformat() if msg.date else 'Unknown'
                    }
                    unmapped_emails.append(unmapped_info)
                
                    print(f"✗ Unmapped: {msg.subject[:50]}... (from: {msg.from_})")
                    
                    # Mark as read anyway so we don't keep processing it
                    mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)
                    continue
                
                # Optional: Process with LLM if enabled
                if ENABLE_LLM:
                    try:
                        from llm_processor import process_with_ollama
                        OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
                        llm_result = process_with_ollama(newsletter, OLLAMA_MODEL)
                        newsletter.update(llm_result)
                        print(f"  LLM processing complete")
                    except ImportError:
                        print(f"  Warning: LLM enabled but llm_processor not found")
                    except Exception as e:
                        print(f"  Warning: LLM processing failed: {e}")
                
                # Insert into Supabase
                supabase.table("newsletters").insert(newsletter).execute()
                
                # Mark as read
                mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)
                
                processed_count += 1
                print(f"  ✓ Stored in database")
                
            except Exception as e:
                print(f"✗ Error processing {msg.uid}: {e}")
                continue
        
        if unmapped_emails:
            save_unmapped_report(unmapped_emails)

        # Summary report
        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] Processing Complete!")
        print(f"{'='*60}")
        print(f"✓ Processed & Stored: {processed_count}")
        print(f"⊘ Skipped (duplicates): {skipped_count}")
        print(f"✗ Unmapped (no source): {unmapped_count}")
        print(f"{'='*60}")
        

if __name__ == "__main__":
    process_new_newsletters()