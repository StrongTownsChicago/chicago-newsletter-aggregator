from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()


def get_supabase_client() -> Client:
    """Get initialized Supabase client."""
    url: str | None = os.getenv("SUPABASE_URL")
    key: str | None = os.getenv("SUPABASE_SERVICE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

    return create_client(url, key)
