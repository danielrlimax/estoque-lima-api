from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin
from app.schemas.admin import (
    AdminAsaasEventResponse,
    AdminPlatformSummaryResponse,
    AdminSubscriptionResponse,
    AdminTenantResponse,
    AdminUpdateSubscriptionStatusRequest,
    AdminUpdateTenantStatusRequest,
)

router = APIRouter(prefix="/admin", tags=["Platform Admin"])


def require_platform_admin(current_user: dict):
    """
    Admin da plataforma.

    Para a v1, liberamos pelo e-mail.
    Depois podemos evoluir para uma tabela platform_admins.
    """
    allowed_admin_emails = {
        "d175259@dac.unicamp.br",
    }

    email = current_user.get("email")

    if email not in allowed_admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administrador da plataforma.",
        )


@router.get("/summary", response_model=AdminPlatformSummaryResponse)
def get_platform_summary(
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        tenants_response = (
            supabase
            .table("tenants")
            .select("id, status")
            .execute()
        )

        subscriptions_response = (
            supabase
            .table("subscriptions")
            .select("id, status")
            .execute()
        )

        tenants = tenants_response.data or []
        subscriptions = subscriptions_response.data or []

        return {
            "total_tenants": len(tenants),
            "active_tenants": len([t for t in tenants if t["status"] == "active"]),
            "trialing_tenants": len([t for t in tenants if t["status"] == "trialing"]),
            "suspended_tenants": len([t for t in tenants if t["status"] == "suspended"]),
            "canceled_tenants": len([t for t in tenants if t["status"] == "canceled"]),
            "total_subscriptions": len(subscriptions),
            "active_subscriptions": len([s for s in subscriptions if s["status"] == "active"]),
            "trialing_subscriptions": len([s for s in subscriptions if s["status"] == "trialing"]),
            "past_due_subscriptions": len([s for s in subscriptions if s["status"] == "past_due"]),
            "canceled_subscriptions": len([s for s in subscriptions if s["status"] == "canceled"]),
        }

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/tenants", response_model=list[AdminTenantResponse])
def list_platform_tenants(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("tenants")
            .select("id, name, slug, email, phone, document, status, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.patch("/tenants/{tenant_id}/status", response_model=AdminTenantResponse)
def update_tenant_status(
    tenant_id: str,
    payload: AdminUpdateTenantStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    allowed_status = {"trialing", "active", "suspended", "canceled"}

    if payload.status not in allowed_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status inválido.",
        )

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("tenants")
            .update({"status": payload.status})
            .eq("id", tenant_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant não encontrado.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/subscriptions", response_model=list[AdminSubscriptionResponse])
def list_platform_subscriptions(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("subscriptions")
            .select(
                "id, tenant_id, status, provider, asaas_customer_id, "
                "asaas_subscription_id, trial_ends_at, current_period_end, "
                "created_at, tenants(name)"
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        result = []

        for item in response.data or []:
            tenant = item.get("tenants") or {}

            result.append({
                "id": item["id"],
                "tenant_id": item["tenant_id"],
                "tenant_name": tenant.get("name"),
                "status": item["status"],
                "provider": item["provider"],
                "asaas_customer_id": item.get("asaas_customer_id"),
                "asaas_subscription_id": item.get("asaas_subscription_id"),
                "trial_ends_at": item.get("trial_ends_at"),
                "current_period_end": item.get("current_period_end"),
                "created_at": item["created_at"],
            })

        return result

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.patch("/subscriptions/{subscription_id}/status", response_model=AdminSubscriptionResponse)
def update_subscription_status(
    subscription_id: str,
    payload: AdminUpdateSubscriptionStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    allowed_status = {"trialing", "active", "past_due", "canceled", "expired"}

    if payload.status not in allowed_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status inválido.",
        )

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("subscriptions")
            .update({"status": payload.status})
            .eq("id", subscription_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada.",
            )

        item = response.data[0]

        tenant_response = (
            supabase
            .table("tenants")
            .select("name")
            .eq("id", item["tenant_id"])
            .limit(1)
            .execute()
        )

        tenant_name = None

        if tenant_response.data:
            tenant_name = tenant_response.data[0].get("name")

        return {
            "id": item["id"],
            "tenant_id": item["tenant_id"],
            "tenant_name": tenant_name,
            "status": item["status"],
            "provider": item["provider"],
            "asaas_customer_id": item.get("asaas_customer_id"),
            "asaas_subscription_id": item.get("asaas_subscription_id"),
            "trial_ends_at": item.get("trial_ends_at"),
            "current_period_end": item.get("current_period_end"),
            "created_at": item["created_at"],
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/asaas-events", response_model=list[AdminAsaasEventResponse])
def list_asaas_events(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("asaas_events")
            .select(
                "id, event_id, event_type, payment_id, subscription_id, "
                "customer_id, processed, processed_at, created_at"
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )