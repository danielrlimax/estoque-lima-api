from fastapi import HTTPException, status

from app.core.config import get_platform_admin_emails
from app.db.supabase_client import get_supabase_admin


MANAGER_ROLES = {"owner", "admin", "manager"}
OWNER_ROLES = {"owner"}


def get_current_user_id(current_user: dict) -> str:
    user_id = current_user.get("id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não autenticado.",
        )

    return str(user_id)


def get_current_user_email(current_user: dict) -> str:
    return (current_user.get("email") or "").strip().lower()


def is_platform_admin(current_user: dict) -> bool:
    email = get_current_user_email(current_user)

    if not email:
        return False

    return email in get_platform_admin_emails()


def require_platform_admin(current_user: dict):
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administrador da plataforma.",
        )


def get_tenant_membership(current_user: dict, tenant_id: str) -> dict | None:
    user_id = get_current_user_id(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("tenant_members")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao validar vínculo com o estabelecimento.",
        )


def ensure_user_belongs_to_tenant(
    current_user: dict,
    tenant_id: str,
    *,
    allow_platform_admin: bool = False,
) -> dict:
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id é obrigatório.",
        )

    if allow_platform_admin and is_platform_admin(current_user):
        return {
            "tenant_id": tenant_id,
            "user_id": current_user.get("id"),
            "role": "platform_admin",
            "platform_admin": True,
        }

    membership = get_tenant_membership(current_user, tenant_id)

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a este estabelecimento.",
        )

    return membership


def ensure_user_can_manage_tenant(
    current_user: dict,
    tenant_id: str,
    *,
    allow_platform_admin: bool = False,
) -> dict:
    membership = ensure_user_belongs_to_tenant(
        current_user,
        tenant_id,
        allow_platform_admin=allow_platform_admin,
    )

    role = membership.get("role")

    if role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para gerenciar este estabelecimento.",
        )

    return membership


def ensure_user_is_tenant_owner(
    current_user: dict,
    tenant_id: str,
    *,
    allow_platform_admin: bool = False,
) -> dict:
    membership = ensure_user_belongs_to_tenant(
        current_user,
        tenant_id,
        allow_platform_admin=allow_platform_admin,
    )

    role = membership.get("role")

    if role not in OWNER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o dono do estabelecimento pode executar esta ação.",
        )

    return membership


def ensure_tenant_is_accessible(tenant_id: str) -> dict:
    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("tenants")
            .select("*")
            .eq("id", tenant_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estabelecimento não encontrado.",
            )

        tenant = response.data[0]
        tenant_status = tenant.get("status")

        if tenant_status in {"suspended", "banned", "canceled", "cancelled"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este estabelecimento está bloqueado.",
            )

        return tenant

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao validar estabelecimento.",
        )


def ensure_safe_tenant_access(
    current_user: dict,
    tenant_id: str,
    *,
    allow_platform_admin: bool = False,
) -> dict:
    membership = ensure_user_belongs_to_tenant(
        current_user,
        tenant_id,
        allow_platform_admin=allow_platform_admin,
    )

    ensure_tenant_is_accessible(tenant_id)

    return membership


def ensure_safe_tenant_management(
    current_user: dict,
    tenant_id: str,
    *,
    allow_platform_admin: bool = False,
) -> dict:
    membership = ensure_user_can_manage_tenant(
        current_user,
        tenant_id,
        allow_platform_admin=allow_platform_admin,
    )

    ensure_tenant_is_accessible(tenant_id)

    return membership