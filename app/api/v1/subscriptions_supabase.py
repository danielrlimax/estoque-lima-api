from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.subscription import SubscriptionStatusResponse

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def parse_datetime(value: str | None):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/status", response_model=SubscriptionStatusResponse)
def get_subscription_status(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        member_response = (
            supabase
            .table("tenant_members")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("user_id", current_user["id"])
            .eq("active", True)
            .limit(1)
            .execute()
        )

        if not member_response.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não pertence a este tenant.",
            )

        response = (
            supabase
            .table("subscriptions")
            .select(
                "tenant_id, status, trial_ends_at, current_period_end, "
                "asaas_customer_id, asaas_subscription_id, "
                "plans(code, name)"
            )
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada.",
            )

        subscription = response.data[0]

        status_value = subscription["status"]
        now = datetime.now(timezone.utc)

        trial_ends_at = parse_datetime(subscription.get("trial_ends_at"))
        current_period_end = parse_datetime(subscription.get("current_period_end"))

        is_active = False

        if status_value == "active":
            is_active = True

        elif status_value == "trialing":
            limit_date = trial_ends_at or current_period_end

            if limit_date and limit_date >= now:
                is_active = True

        plan = subscription.get("plans") or {}

        return {
            "tenant_id": subscription["tenant_id"],
            "status": status_value,
            "is_active": is_active,
            "plan_code": plan.get("code"),
            "plan_name": plan.get("name"),
            "trial_ends_at": subscription.get("trial_ends_at"),
            "current_period_end": subscription.get("current_period_end"),
            "asaas_customer_id": subscription.get("asaas_customer_id"),
            "asaas_subscription_id": subscription.get("asaas_subscription_id"),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )