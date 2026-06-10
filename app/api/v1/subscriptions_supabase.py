from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.core.audit import write_audit_log
from app.core.security import get_current_user
from app.core.tenant_security import ensure_safe_tenant_access, ensure_safe_tenant_management
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


class ChangePlanRequest(BaseModel):
    tenant_id: str
    plan_id: str


def get_active_plans() -> list[dict]:
    supabase = get_supabase_admin()

    try:
        response = (
            supabase
            .table("plans")
            .select("*")
            .eq("active", True)
            .order("price_monthly", desc=False)
            .execute()
        )

        return response.data or []

    except Exception:
        response = (
            supabase
            .table("plans")
            .select("*")
            .order("price_monthly", desc=False)
            .execute()
        )

        return response.data or []


def get_plan_by_id(plan_id: str) -> dict:
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plano não encontrado.",
        )

    return response.data[0]


def get_latest_subscription(tenant_id: str) -> dict | None:
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


def count_products(tenant_id: str) -> int:
    supabase = get_supabase_admin()

    try:
        response = (
            supabase
            .table("products")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .execute()
        )

        return response.count or 0

    except Exception:
        response = (
            supabase
            .table("products")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return response.count or 0


def count_users(tenant_id: str) -> int:
    supabase = get_supabase_admin()

    try:
        response = (
            supabase
            .table("tenant_members")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .execute()
        )

        return response.count or 0

    except Exception:
        response = (
            supabase
            .table("tenant_members")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return response.count or 0


def is_subscription_active(subscription: dict | None) -> bool:
    if not subscription:
        return False

    return subscription.get("status") in {
        "active",
        "trialing",
        "paid",
        "manual",
    }


def create_manual_subscription(tenant_id: str, plan_id: str) -> dict:
    supabase = get_supabase_admin()

    now = datetime.now(timezone.utc).isoformat()

    full_payload = {
        "tenant_id": tenant_id,
        "plan_id": plan_id,
        "provider": "manual",
        "status": "active",
        "metadata": {
            "source": "manual_plan_change",
            "changed_at": now,
        },
    }

    try:
        response = (
            supabase
            .table("subscriptions")
            .insert(full_payload)
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception:
        minimal_payload = {
            "tenant_id": tenant_id,
            "plan_id": plan_id,
            "status": "active",
        }

        response = (
            supabase
            .table("subscriptions")
            .insert(minimal_payload)
            .execute()
        )

        if response.data:
            return response.data[0]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Não foi possível criar assinatura manual.",
    )


def update_subscription_plan(subscription_id: str, plan_id: str) -> dict:
    supabase = get_supabase_admin()

    update_payload = {
        "plan_id": plan_id,
        "status": "active",
    }

    try:
        response = (
            supabase
            .table("subscriptions")
            .update({
                **update_payload,
                "provider": "manual",
                "metadata": {
                    "source": "manual_plan_change",
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                },
            })
            .eq("id", subscription_id)
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception:
        response = (
            supabase
            .table("subscriptions")
            .update(update_payload)
            .eq("id", subscription_id)
            .execute()
        )

        if response.data:
            return response.data[0]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Não foi possível atualizar assinatura.",
    )


@router.get("/plans")
def list_plans(current_user: dict = Depends(get_current_user)):
    plans = get_active_plans()

    return plans


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

    plan = None

    if subscription.get("plan_id"):
        try:
            plan = get_plan_by_id(subscription["plan_id"])
        except HTTPException:
            plan = None

    return {
        "tenant_id": tenant_id,
        "status": subscription.get("status"),
        "is_active": is_subscription_active(subscription),
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

    subscription = get_latest_subscription(tenant_id)

    if not subscription or not subscription.get("plan_id"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura não encontrada para este estabelecimento.",
        )

    plan = get_plan_by_id(subscription["plan_id"])

    products_count = count_products(tenant_id)
    users_count = count_users(tenant_id)

    max_products = plan.get("max_products")
    max_users = plan.get("max_users")

    return {
        "tenant_id": tenant_id,
        "plan": {
            "id": plan.get("id"),
            "code": plan.get("code"),
            "name": plan.get("name"),
            "price_monthly": plan.get("price_monthly"),
            "max_products": max_products,
            "max_users": max_users,
        },
        "usage": {
            "products": products_count,
            "users": users_count,
        },
        "limits": {
            "products": max_products,
            "users": max_users,
        },
        "remaining": {
            "products": None if max_products is None else max(max_products - products_count, 0),
            "users": None if max_users is None else max(max_users - users_count, 0),
        },
    }


@router.post("/change-plan")
def change_plan(
    payload: ChangePlanRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_management(current_user, payload.tenant_id)

    plan = get_plan_by_id(payload.plan_id)
    subscription = get_latest_subscription(payload.tenant_id)

    if subscription:
        updated_subscription = update_subscription_plan(
            subscription_id=subscription["id"],
            plan_id=payload.plan_id,
        )
    else:
        updated_subscription = create_manual_subscription(
            tenant_id=payload.tenant_id,
            plan_id=payload.plan_id,
        )

    write_audit_log(
        tenant_id=payload.tenant_id,
        action="subscription.change_plan",
        entity_type="subscription",
        entity_id=updated_subscription.get("id"),
        description=f"Plano alterado para {plan.get('name')}",
        metadata={
            "plan": plan,
            "subscription": updated_subscription,
            "mode": "manual",
        },
        current_user=current_user,
        request=request,
    )

    return {
        "message": "Plano alterado com sucesso.",
        "subscription": updated_subscription,
        "plan": plan,
    }