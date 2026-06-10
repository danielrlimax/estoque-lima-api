from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_platform_admin_emails
from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/admin/financeiro", tags=["Admin Financeiro"])


def require_platform_admin(current_user: dict):
    allowed_emails = get_platform_admin_emails()
    email = (current_user.get("email") or "").strip().lower()

    if email not in allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administrador da plataforma.",
        )


def money(value: Any) -> float:
    try:
        if value is None:
            return 0.0

        if isinstance(value, Decimal):
            return float(value)

        return float(value)
    except Exception:
        return 0.0


def extract_asaas_payment_value(payload: dict | None) -> float:
    if not payload:
        return 0.0

    payment = payload.get("payment")

    if isinstance(payment, dict):
        return money(
            payment.get("value")
            or payment.get("netValue")
            or payment.get("originalValue")
        )

    return money(
        payload.get("value")
        or payload.get("netValue")
        or payload.get("originalValue")
    )


@router.get("")
def get_financeiro(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        plans_response = (
            supabase
            .table("plans")
            .select("*")
            .execute()
        )

        subscriptions_response = (
            supabase
            .table("subscriptions")
            .select("*")
            .execute()
        )

        tenants_response = (
            supabase
            .table("tenants")
            .select("id,status")
            .execute()
        )

        coupons_response = (
            supabase
            .table("coupons")
            .select("id,active")
            .execute()
        )

        asaas_events_response = (
            supabase
            .table("asaas_events")
            .select("*")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        plans = plans_response.data or []
        subscriptions = subscriptions_response.data or []
        tenants = tenants_response.data or []
        coupons = coupons_response.data or []
        asaas_events = asaas_events_response.data or []

        plans_by_id = {
            str(plan.get("id")): plan
            for plan in plans
            if plan.get("id")
        }

        active_statuses = {"active"}
        revenue_statuses = {"active"}
        trial_statuses = {"trialing"}
        past_due_statuses = {"past_due", "overdue"}
        canceled_statuses = {"canceled", "cancelled"}

        active_subscriptions = [
            subscription
            for subscription in subscriptions
            if subscription.get("status") in active_statuses
        ]

        trialing_subscriptions = [
            subscription
            for subscription in subscriptions
            if subscription.get("status") in trial_statuses
        ]

        past_due_subscriptions = [
            subscription
            for subscription in subscriptions
            if subscription.get("status") in past_due_statuses
        ]

        canceled_subscriptions = [
            subscription
            for subscription in subscriptions
            if subscription.get("status") in canceled_statuses
        ]

        mrr = 0.0
        revenue_by_plan_map: dict[str, dict] = {}

        for subscription in subscriptions:
            status_value = subscription.get("status")

            plan_id = subscription.get("plan_id")
            plan = plans_by_id.get(str(plan_id))

            if not plan:
                continue

            plan_price = money(plan.get("price_monthly"))

            plan_key = str(plan.get("id"))

            if plan_key not in revenue_by_plan_map:
                revenue_by_plan_map[plan_key] = {
                    "plan_id": plan.get("id"),
                    "plan_code": plan.get("code"),
                    "plan_name": plan.get("name"),
                    "price_monthly": plan_price,
                    "active_subscriptions": 0,
                    "trialing_subscriptions": 0,
                    "past_due_subscriptions": 0,
                    "canceled_subscriptions": 0,
                    "mrr": 0.0,
                }

            if status_value in revenue_statuses:
                mrr += plan_price
                revenue_by_plan_map[plan_key]["active_subscriptions"] += 1
                revenue_by_plan_map[plan_key]["mrr"] += plan_price

            elif status_value in trial_statuses:
                revenue_by_plan_map[plan_key]["trialing_subscriptions"] += 1

            elif status_value in past_due_statuses:
                revenue_by_plan_map[plan_key]["past_due_subscriptions"] += 1

            elif status_value in canceled_statuses:
                revenue_by_plan_map[plan_key]["canceled_subscriptions"] += 1

        arr = mrr * 12

        estimated_lost_mrr = 0.0

        for subscription in canceled_subscriptions:
            plan_id = subscription.get("plan_id")
            plan = plans_by_id.get(str(plan_id))

            if plan:
                estimated_lost_mrr += money(plan.get("price_monthly"))

        confirmed_payment_events = [
            event
            for event in asaas_events
            if event.get("event") in {
                "PAYMENT_CONFIRMED",
                "PAYMENT_RECEIVED",
                "PAYMENT_APPROVED_BY_RISK_ANALYSIS",
            }
        ]

        received_from_asaas_events = 0.0

        recent_payments = []

        for event in confirmed_payment_events:
            payload = event.get("payload") or {}
            value = extract_asaas_payment_value(payload)
            received_from_asaas_events += value

            payment = payload.get("payment") if isinstance(payload, dict) else {}

            if not isinstance(payment, dict):
                payment = {}

            recent_payments.append({
                "id": event.get("id"),
                "event": event.get("event"),
                "value": value,
                "customer": (
                    payment.get("customer")
                    or payload.get("customer")
                    if isinstance(payload, dict)
                    else None
                ),
                "billing_type": (
                    payment.get("billingType")
                    or payload.get("billingType")
                    if isinstance(payload, dict)
                    else None
                ),
                "created_at": event.get("created_at"),
            })

        total_tenants = len(tenants)

        active_tenants = len([
            tenant
            for tenant in tenants
            if tenant.get("status") == "active"
        ])

        banned_tenants = len([
            tenant
            for tenant in tenants
            if tenant.get("status") == "banned"
        ])

        suspended_tenants = len([
            tenant
            for tenant in tenants
            if tenant.get("status") == "suspended"
        ])

        active_coupons = len([
            coupon
            for coupon in coupons
            if coupon.get("active") is True
        ])

        revenue_by_plan = sorted(
            revenue_by_plan_map.values(),
            key=lambda item: item["mrr"],
            reverse=True,
        )

        average_revenue_per_active_subscription = (
            mrr / len(active_subscriptions)
            if active_subscriptions
            else 0.0
        )

        return {
            "mrr": round(mrr, 2),
            "arr": round(arr, 2),
            "estimated_lost_mrr": round(estimated_lost_mrr, 2),
            "received_from_asaas_events": round(received_from_asaas_events, 2),
            "average_revenue_per_active_subscription": round(
                average_revenue_per_active_subscription,
                2,
            ),

            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "suspended_tenants": suspended_tenants,
            "banned_tenants": banned_tenants,

            "total_plans": len(plans),
            "active_plans": len([
                plan
                for plan in plans
                if plan.get("active") is True
            ]),

            "total_subscriptions": len(subscriptions),
            "active_subscriptions": len(active_subscriptions),
            "trialing_subscriptions": len(trialing_subscriptions),
            "past_due_subscriptions": len(past_due_subscriptions),
            "canceled_subscriptions": len(canceled_subscriptions),

            "total_coupons": len(coupons),
            "active_coupons": active_coupons,

            "total_asaas_events": len(asaas_events),
            "confirmed_payment_events": len(confirmed_payment_events),

            "revenue_by_plan": revenue_by_plan,
            "recent_payments": recent_payments[:10],
        }

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )