import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_platform_admin_emails
from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin
from app.schemas.admin import (
    AdminAddTenantMemberRequest,
    AdminAsaasEventResponse,
    AdminCouponCreateRequest,
    AdminCouponResponse,
    AdminCouponUpdateRequest,
    AdminMeResponse,
    AdminPlatformSummaryResponse,
    AdminSubscriptionResponse,
    AdminTenantCreateRequest,
    AdminTenantMemberResponse,
    AdminTenantResponse,
    AdminUpdateSubscriptionStatusRequest,
    AdminUpdateTenantStatusRequest,
)

router = APIRouter(prefix="/admin", tags=["Platform Admin"])


def require_platform_admin(current_user: dict):
    allowed_emails = get_platform_admin_emails()
    email = (current_user.get("email") or "").strip().lower()

    if email not in allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso permitido apenas para administrador da plataforma.",
        )


def make_slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


def validate_tenant_status(value: str):
    allowed = {"trialing", "active", "suspended", "canceled", "banned"}

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status de estabelecimento inválido.",
        )


def validate_subscription_status(value: str):
    allowed = {"trialing", "active", "past_due", "canceled", "expired"}

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status de assinatura inválido.",
        )


def validate_role(value: str):
    allowed = {"owner", "admin", "manager", "cashier", "viewer"}

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Papel de usuário inválido.",
        )


def validate_coupon_type(value: str):
    allowed = {"percentage", "fixed"}

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de cupom inválido.",
        )


@router.get("/me", response_model=AdminMeResponse)
def get_admin_me(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    return {
        "is_admin": True,
        "email": current_user.get("email"),
    }


@router.get("/summary", response_model=AdminPlatformSummaryResponse)
def get_platform_summary(current_user: dict = Depends(get_current_user)):
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

        coupons_response = (
            supabase
            .table("coupons")
            .select("id, active")
            .execute()
        )

        events_response = (
            supabase
            .table("asaas_events")
            .select("id")
            .execute()
        )

        tenants = tenants_response.data or []
        subscriptions = subscriptions_response.data or []
        coupons = coupons_response.data or []
        events = events_response.data or []

        return {
            "total_tenants": len(tenants),
            "active_tenants": len([t for t in tenants if t["status"] == "active"]),
            "trialing_tenants": len([t for t in tenants if t["status"] == "trialing"]),
            "suspended_tenants": len([t for t in tenants if t["status"] == "suspended"]),
            "canceled_tenants": len([t for t in tenants if t["status"] == "canceled"]),
            "banned_tenants": len([t for t in tenants if t["status"] == "banned"]),
            "total_subscriptions": len(subscriptions),
            "active_subscriptions": len([s for s in subscriptions if s["status"] == "active"]),
            "trialing_subscriptions": len([s for s in subscriptions if s["status"] == "trialing"]),
            "past_due_subscriptions": len([s for s in subscriptions if s["status"] == "past_due"]),
            "canceled_subscriptions": len([s for s in subscriptions if s["status"] == "canceled"]),
            "total_coupons": len(coupons),
            "active_coupons": len([c for c in coupons if c["active"]]),
            "total_asaas_events": len(events),
        }

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/tenants", response_model=list[AdminTenantResponse])
def list_platform_tenants(
    limit: int = Query(default=100, ge=1, le=500),
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


@router.post("/tenants", response_model=AdminTenantResponse)
def create_platform_tenant(
    payload: AdminTenantCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    validate_tenant_status(payload.status)

    try:
        supabase = get_supabase_admin()

        slug = make_slug(payload.slug or payload.name)

        tenant_response = (
            supabase
            .table("tenants")
            .insert({
                "name": payload.name,
                "slug": slug,
                "email": str(payload.email) if payload.email else None,
                "phone": payload.phone,
                "document": payload.document,
                "status": payload.status,
            })
            .execute()
        )

        if not tenant_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar o estabelecimento.",
            )

        tenant = tenant_response.data[0]

        plan_response = (
            supabase
            .table("plans")
            .select("id")
            .eq("code", "starter")
            .limit(1)
            .execute()
        )

        if plan_response.data:
            plan_id = plan_response.data[0]["id"]
            trial_end = datetime.now(timezone.utc) + timedelta(days=7)

            existing_subscription = (
                supabase
                .table("subscriptions")
                .select("id")
                .eq("tenant_id", tenant["id"])
                .limit(1)
                .execute()
            )

            if not existing_subscription.data:
                supabase.table("subscriptions").insert({
                    "tenant_id": tenant["id"],
                    "plan_id": plan_id,
                    "status": "trialing",
                    "provider": "manual",
                    "trial_ends_at": trial_end.isoformat(),
                    "current_period_end": trial_end.isoformat(),
                }).execute()

        if payload.owner_email:
            profile_response = (
                supabase
                .table("profiles")
                .select("id, email")
                .eq("email", str(payload.owner_email))
                .limit(1)
                .execute()
            )

            if profile_response.data:
                owner_profile = profile_response.data[0]

                supabase.table("tenant_members").upsert({
                    "tenant_id": tenant["id"],
                    "user_id": owner_profile["id"],
                    "role": "owner",
                    "active": True,
                }).execute()

        return tenant

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/tenants/{tenant_id}/status", response_model=AdminTenantResponse)
def update_tenant_status(
    tenant_id: str,
    payload: AdminUpdateTenantStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    validate_tenant_status(payload.status)

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
                detail="Estabelecimento não encontrado.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.post(
    "/tenants/{tenant_id}/members",
    response_model=AdminTenantMemberResponse,
)
def add_tenant_member(
    tenant_id: str,
    payload: AdminAddTenantMemberRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    validate_role(payload.role)

    try:
        supabase = get_supabase_admin()

        profile_response = (
            supabase
            .table("profiles")
            .select("id, email")
            .eq("email", str(payload.email))
            .limit(1)
            .execute()
        )

        if not profile_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado em profiles. Peça para ele criar conta primeiro.",
            )

        profile = profile_response.data[0]

        response = (
            supabase
            .table("tenant_members")
            .upsert({
                "tenant_id": tenant_id,
                "user_id": profile["id"],
                "role": payload.role,
                "active": True,
            })
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível adicionar membro ao estabelecimento.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.get("/subscriptions", response_model=list[AdminSubscriptionResponse])
def list_platform_subscriptions(
    limit: int = Query(default=100, ge=1, le=500),
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
    validate_subscription_status(payload.status)

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


@router.get("/coupons", response_model=list[AdminCouponResponse])
def list_coupons(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("coupons")
            .select(
                "id, code, description, type, value, active, max_uses, "
                "used_count, valid_from, valid_until, created_at"
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


@router.post("/coupons", response_model=AdminCouponResponse)
def create_coupon(
    payload: AdminCouponCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    validate_coupon_type(payload.type)

    try:
        supabase = get_supabase_admin()

        code = payload.code.strip().upper()

        response = (
            supabase
            .table("coupons")
            .insert({
                "code": code,
                "description": payload.description,
                "type": payload.type,
                "value": str(payload.value),
                "active": payload.active,
                "max_uses": payload.max_uses,
                "used_count": 0,
                "valid_from": payload.valid_from,
                "valid_until": payload.valid_until,
            })
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar cupom.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/coupons/{coupon_id}", response_model=AdminCouponResponse)
def update_coupon(
    coupon_id: str,
    payload: AdminCouponUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        update_data = payload.model_dump(exclude_unset=True)

        if "type" in update_data and update_data["type"] is not None:
            validate_coupon_type(update_data["type"])

        if "value" in update_data and isinstance(update_data["value"], Decimal):
            update_data["value"] = str(update_data["value"])

        response = (
            supabase
            .table("coupons")
            .update(update_data)
            .eq("id", coupon_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cupom não encontrado.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.delete("/coupons/{coupon_id}", response_model=AdminCouponResponse)
def disable_coupon(
    coupon_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("coupons")
            .update({"active": False})
            .eq("id", coupon_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cupom não encontrado.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.get("/asaas-events", response_model=list[AdminAsaasEventResponse])
def list_asaas_events(
    limit: int = Query(default=100, ge=1, le=500),
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