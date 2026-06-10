from typing import Any

from fastapi import Request

from app.db.supabase_client import get_supabase_admin


def get_request_ip(request: Request | None) -> str | None:
    if not request:
        return None

    forwarded_for = request.headers.get("x-forwarded-for")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")

    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return None


def get_user_agent(request: Request | None) -> str | None:
    if not request:
        return None

    return request.headers.get("user-agent")


def write_audit_log(
    *,
    action: str,
    entity_type: str,
    tenant_id: str | None = None,
    entity_id: str | None = None,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
    current_user: dict | None = None,
    request: Request | None = None,
):
    """
    Registra uma ação importante no sistema.

    Não deve quebrar a ação principal caso o log falhe.
    Por isso, qualquer erro é engolido silenciosamente.
    """

    try:
        supabase = get_supabase_admin()

        actor_user_id = None
        actor_email = None

        if current_user:
            actor_user_id = current_user.get("id")
            actor_email = current_user.get("email")

        supabase.table("audit_logs").insert(
            {
                "tenant_id": tenant_id,
                "actor_user_id": actor_user_id,
                "actor_email": actor_email,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "description": description,
                "metadata": metadata or {},
                "ip_address": get_request_ip(request),
                "user_agent": get_user_agent(request),
            }
        ).execute()

    except Exception:
        return None