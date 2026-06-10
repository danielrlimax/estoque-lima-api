from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.plan_limits import get_plan_usage
from app.core.security import get_current_user
from app.core.tenant_security import ensure_safe_tenant_access
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


def get_latest_subscription(tenant_id: str) -> dict | None:
    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("subscriptions")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao consultar assinatura.",
        )


def get_plan_by_id(plan_id: str | None) -> dict | None:
    if not plan_id:
        return None

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("plans")
            .select("*")
            .eq("id", plan_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao consultar plano.",
        )


@router.get("/status")
def get_subscription_status(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_access(current_user, tenant_id)

    subscription = get_latest_subscription(tenant_id)

    if not subscription:
        return {
            "tenant_id": tenant_id,
            "status": "none",
            "is_active": False,
            "plan_code": None,
            "plan_name": None,
            "trial_ends_at": None,
            "current_period_end": None,
            "asaas_customer_id": None,
            "asaas_subscription_id": None,
        }

    plan = get_plan_by_id(subscription.get("plan_id"))

    subscription_status = subscription.get("status") or "none"

    return {
        "tenant_id": tenant_id,
        "status": subscription_status,
        "is_active": subscription_status in ACTIVE_SUBSCRIPTION_STATUSES,
        "plan_code": plan.get("code") if plan else None,
        "plan_name": plan.get("name") if plan else None,
        "trial_ends_at": subscription.get("trial_ends_at"),
        "current_period_end": subscription.get("current_period_end"),
        "asaas_customer_id": subscription.get("asaas_customer_id"),
        "asaas_subscription_id": subscription.get("asaas_subscription_id"),
    }


@router.get("/usage")
def get_subscription_usage(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_access(current_user, tenant_id)

    return get_plan_usage(tenant_id)