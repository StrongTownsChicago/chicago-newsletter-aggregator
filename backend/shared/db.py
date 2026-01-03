from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

def get_supabase_client():
    """Get initialized Supabase client"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    return create_client(url, key)