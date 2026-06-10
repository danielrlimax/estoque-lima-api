from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_platform_admin_emails
from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/admin/audit-logs", tags=["Audit Logs"])


def require_platform_admin(current_user: dict):
    allowed_emails = get_platform_admin_emails()
    email = (current_user.get("email") or "").strip().lower()

    if email not in allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administrador da plataforma.",
        )


@router.get("")
def list_audit_logs(
    tenant_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_email: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        query = (
            supabase
            .table("audit_logs")
            .select(
                "id, tenant_id, actor_user_id, actor_email, action, "
                "entity_type, entity_id, description, metadata, "
                "ip_address, user_agent, created_at"
            )
            .order("created_at", desc=True)
            .limit(limit)
        )

        if tenant_id:
            query = query.eq("tenant_id", tenant_id)

        if action:
            query = query.eq("action", action)

        if entity_type:
            query = query.eq("entity_type", entity_type)

        if actor_email:
            query = query.ilike("actor_email", f"%{actor_email}%")

        response = query.execute()

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )