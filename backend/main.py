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
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"  # Optional LLM processing

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def newsletter_exists(email_uid: str) -> bool:
    """Check if newsletter already processed"""
    result = supabase.table("newsletters").select("id").eq("email_uid", email_uid).execute()
    return len(result.data) > 0

def process_new_newsletters():
    """Main processing function"""
    
    print(f"[{datetime.now()}] Starting newsletter ingestion...")
    
    # Connect to Gmail
    with MailBox('imap.gmail.com').login(GMAIL_ADDRESS, GMAIL_PASSWORD) as mailbox:
        
        # Fetch unread emails (or use seen=False to process all unread)
        messages = mailbox.fetch(AND(seen=False))
        # Below line can be uncommented to process all emails for testing
        #messages = mailbox.fetch()
        
        processed_count = 0
        skipped_count = 0
        
        for msg in messages:
            try:
                # Skip if already processed
                if newsletter_exists(msg.uid):
                    print(f"Skipping duplicate: {msg.uid}")
                    skipped_count += 1
                    continue
                
                # Parse email
                print(f"Processing: {msg.subject}")
                newsletter = parse_newsletter(msg, supabase)
                
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
                print(f"✓ Processed: {newsletter['subject'][:50]}...")
                
            except Exception as e:
                print(f"✗ Error processing {msg.uid}: {e}")
                continue
        
        print(f"\n[{datetime.now()}] Complete!")
        print(f"Processed: {processed_count}, Skipped: {skipped_count}")

if __name__ == "__main__":
    process_new_newsletters()