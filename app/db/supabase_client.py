from supabase import Client, create_client

from app.core.config import settings


def get_supabase() -> Client:
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )


def get_supabase_with_token(access_token: str) -> Client:
    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )

    client.postgrest.auth(access_token)

    return client


def get_supabase_admin() -> Client:
    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY não configurada no .env")

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )