from supabase import create_client, Client
from app.core.config import get_settings
from functools import lru_cache


@lru_cache()
def get_supabase_client() -> Client:
    """Public client using anon key — for frontend-safe operations."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache()
def get_supabase_admin() -> Client:
    """Admin client using service role key — BACKEND ONLY, never expose to frontend."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
