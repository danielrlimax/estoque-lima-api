from datetime import datetime, timedelta, timezone
from typing import Any
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.audit import write_audit_log
from app.core.plan_limits import ensure_user_limit_not_exceeded
from app.core.security import get_current_user
from app.core.tenant_security import require_platform_admin
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str | None = Field(default=None, max_length=120)
    email: str | None = None
    phone: str | None = None
    document: str | None = None
    status: str = Field(
        default="trialing",
        pattern="^(active|trialing|suspended|canceled|cancelled|banned)$",
    )
    owner_email: str | None = None


class TenantStatusUpdateRequest(BaseModel):
    status: str = Field(
        pattern="^(active|trialing|suspended|canceled|cancelled|banned)$"
    )


class AddTenantMemberRequest(BaseModel):
    email: str
    role: str = Field(pattern="^(owner|admin|manager|member)$")


class SubscriptionStatusUpdateRequest(BaseModel):
    status: str = Field(
        pattern="^(active|trialing|past_due|overdue|canceled|cancelled|suspended)$"
    )


class CouponCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    description: str | None = None
    discount_type: str = Field(pattern="^(percent|fixed)$")
    discount_value: float = Field(ge=0)
    max_redemptions: int | None = Field(default=None, ge=1)
    active: bool = True


class CouponUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None
    discount_type: str | None = Field(default=None, pattern="^(percent|fixed)$")
    discount_value: float | None = Field(default=None, ge=0)
    max_redemptions: int | None = Field(default=None, ge=1)
    active: bool | None = None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def normalize_email(value: str | None) -> str | None:
    cleaned = clean_text(value)

    if not cleaned:
        return None

    return cleaned.lower()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    ascii_text = re.sub(r"-+", "-", ascii_text)
    ascii_text = ascii_text.strip("-")

    return ascii_text or "estabelecimento"


def get_unique_slug(base_slug: str) -> str:
    supabase = get_supabase_admin()

    base = slugify(base_slug)
    slug = base
    counter = 2

    while True:
        response = (
            supabase
            .table("tenants")
            .select("id")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )

        if not response.data:
            return slug

        slug = f"{base}-{counter}"
        counter += 1


def get_profile_by_email(email: str) -> dict | None:
    supabase = get_supabase_admin()

    response = (
        supabase
        .table("profiles")
        .select("*")
        .eq("email", email.strip().lower())
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def get_default_plan() -> dict:
    supabase = get_supabase_admin()

    response = (
        supabase
        .table("plans")
        .select("*")
        .eq("code", "starter")
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]

    fallback_response = (
        supabase
        .table("plans")
        .select("*")
        .eq("active", True)
        .order("price_monthly", desc=False)
        .limit(1)
        .execute()
    )

    if fallback_response.data:
        return fallback_response.data[0]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Nenhum plano ativo encontrado. Crie um plano antes de criar estabelecimentos.",
    )


def insert_tenant(
    payload: TenantCreateRequest,
    slug: str,
    owner_user_id: str,
) -> dict:
    supabase = get_supabase_admin()

    full_payload = {
        "name": payload.name.strip(),
        "slug": slug,
        "owner_user_id": owner_user_id,
        "email": normalize_email(payload.email),
        "phone": clean_text(payload.phone),
        "document": clean_text(payload.document),
        "status": payload.status,
        "metadata": {},
    }

    full_payload = {
        key: value
        for key, value in full_payload.items()
        if value is not None
    }

    try:
        response = (
            supabase
            .table("tenants")
            .insert(full_payload)
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception as first_error:
        minimal_payload = {
            "name": payload.name.strip(),
            "slug": slug,
            "owner_user_id": owner_user_id,
            "status": payload.status,
        }

        try:
            response = (
                supabase
                .table("tenants")
                .insert(minimal_payload)
                .execute()
            )

            if response.data:
                return response.data[0]

        except Exception as second_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Não foi possível criar estabelecimento.",
                    "first_error": str(first_error),
                    "second_error": str(second_error),
                },
            )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Não foi possível criar estabelecimento.",
    )


def add_owner_member(tenant_id: str, owner_user_id: str) -> dict | None:
    supabase = get_supabase_admin()

    existing_response = (
        supabase
        .table("tenant_members")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("user_id", owner_user_id)
        .limit(1)
        .execute()
    )

    if existing_response.data:
        return existing_response.data[0]

    try:
        response = (
            supabase
            .table("tenant_members")
            .insert({
                "tenant_id": tenant_id,
                "user_id": owner_user_id,
                "role": "owner",
                "active": True,
            })
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception:
        response = (
            supabase
            .table("tenant_members")
            .insert({
                "tenant_id": tenant_id,
                "user_id": owner_user_id,
                "role": "owner",
            })
            .execute()
        )

        if response.data:
            return response.data[0]

    return None


def create_trial_subscription(tenant_id: str, plan_id: str) -> dict | None:
    supabase = get_supabase_admin()

    now = datetime.now(timezone.utc)
    trial_ends_at = now + timedelta(days=14)
    current_period_end = now + timedelta(days=30)

    try:
        response = (
            supabase
            .table("subscriptions")
            .insert({
                "tenant_id": tenant_id,
                "plan_id": plan_id,
                "provider": "manual",
                "status": "trialing",
                "trial_ends_at": trial_ends_at.isoformat(),
                "current_period_end": current_period_end.isoformat(),
                "metadata": {
                    "created_by": "platform_admin",
                    "source": "admin_panel",
                    "trial_days": 14,
                },
            })
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception:
        response = (
            supabase
            .table("subscriptions")
            .insert({
                "tenant_id": tenant_id,
                "plan_id": plan_id,
                "status": "trialing",
            })
            .execute()
        )

        if response.data:
            return response.data[0]

    return None


def normalize_coupon_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None
    }


@router.get("/me")
def admin_me(current_user: dict = Depends(get_current_user)):
    try:
        require_platform_admin(current_user)

        return {
            "is_admin": True,
            "email": current_user.get("email"),
        }

    except HTTPException as error:
        if error.status_code == status.HTTP_403_FORBIDDEN:
            return {
                "is_admin": False,
                "email": current_user.get("email"),
            }

        raise


@router.get("/summary")
def admin_summary(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        tenants_response = (
            supabase
            .table("tenants")
            .select("id,status")
            .execute()
        )

        subscriptions_response = (
            supabase
            .table("subscriptions")
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
            .select("id")
            .execute()
        )

        tenants = tenants_response.data or []
        subscriptions = subscriptions_response.data or []
        coupons = coupons_response.data or []
        asaas_events = asaas_events_response.data or []

        def count_status(items: list[dict], statuses: set[str]) -> int:
            return len([
                item
                for item in items
                if item.get("status") in statuses
            ])

        return {
            "total_tenants": len(tenants),
            "active_tenants": count_status(tenants, {"active"}),
            "trialing_tenants": count_status(tenants, {"trialing"}),
            "suspended_tenants": count_status(tenants, {"suspended"}),
            "canceled_tenants": count_status(tenants, {"canceled", "cancelled"}),
            "banned_tenants": count_status(tenants, {"banned"}),

            "total_subscriptions": len(subscriptions),
            "active_subscriptions": count_status(subscriptions, {"active"}),
            "trialing_subscriptions": count_status(subscriptions, {"trialing"}),
            "past_due_subscriptions": count_status(
                subscriptions,
                {"past_due", "overdue"},
            ),
            "canceled_subscriptions": count_status(
                subscriptions,
                {"canceled", "cancelled"},
            ),

            "total_coupons": len(coupons),
            "active_coupons": len([
                coupon
                for coupon in coupons
                if coupon.get("active") is True
            ]),

            "total_asaas_events": len(asaas_events),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/tenants")
def list_tenants(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("tenants")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.post("/tenants")
def create_tenant(
    payload: TenantCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        owner_email = normalize_email(payload.owner_email)
        owner_profile = None
        owner_user_id = current_user.get("id")

        if owner_email:
            owner_profile = get_profile_by_email(owner_email)

            if not owner_profile:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        "Usuário dono não encontrado. "
                        "Ele precisa criar conta e fazer login pelo menos uma vez antes."
                    ),
                )

            owner_user_id = owner_profile.get("id")

        if not owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível identificar o dono do estabelecimento.",
            )

        owner_user_id = str(owner_user_id)

        slug = get_unique_slug(payload.slug or payload.name)
        plan = get_default_plan()

        tenant = insert_tenant(
            payload=payload,
            slug=slug,
            owner_user_id=owner_user_id,
        )

        owner_member = add_owner_member(
            tenant_id=tenant["id"],
            owner_user_id=owner_user_id,
        )

        if not owner_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Estabelecimento criado, mas não foi possível vincular o dono.",
            )

        subscription = create_trial_subscription(
            tenant_id=tenant["id"],
            plan_id=plan["id"],
        )

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Estabelecimento criado, mas não foi possível criar assinatura trial.",
            )

        write_audit_log(
            tenant_id=tenant.get("id"),
            action="tenant.create",
            entity_type="tenant",
            entity_id=tenant.get("id"),
            description=f"Estabelecimento criado: {tenant.get('name')}",
            metadata={
                "tenant": tenant,
                "owner_email": owner_email or current_user.get("email"),
                "owner_member": owner_member,
                "subscription": subscription,
                "plan": {
                    "id": plan.get("id"),
                    "code": plan.get("code"),
                    "name": plan.get("name"),
                },
            },
            current_user=current_user,
            request=request,
        )

        return {
            **tenant,
            "owner": owner_profile or {
                "id": current_user.get("id"),
                "email": current_user.get("email"),
            },
            "subscription": subscription,
            "plan": plan,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/tenants/{tenant_id}/status")
def update_tenant_status(
    tenant_id: str,
    payload: TenantStatusUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("tenants")
            .select("*")
            .eq("id", tenant_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estabelecimento não encontrado.",
            )

        old_tenant = old_response.data[0]

        response = (
            supabase
            .table("tenants")
            .update({"status": payload.status})
            .eq("id", tenant_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar estabelecimento.",
            )

        tenant = response.data[0]

        write_audit_log(
            tenant_id=tenant_id,
            action="tenant.status_update",
            entity_type="tenant",
            entity_id=tenant_id,
            description=f"Status alterado para {payload.status}",
            metadata={
                "before": old_tenant,
                "after": tenant,
            },
            current_user=current_user,
            request=request,
        )

        return tenant

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.post("/tenants/{tenant_id}/members")
def add_tenant_member(
    tenant_id: str,
    payload: AddTenantMemberRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        tenant_response = (
            supabase
            .table("tenants")
            .select("*")
            .eq("id", tenant_id)
            .limit(1)
            .execute()
        )

        if not tenant_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estabelecimento não encontrado.",
            )

        ensure_user_limit_not_exceeded(tenant_id)

        profile = get_profile_by_email(payload.email)

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado. Ele precisa criar conta antes.",
            )

        existing_member = (
            supabase
            .table("tenant_members")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("user_id", profile["id"])
            .limit(1)
            .execute()
        )

        if existing_member.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este usuário já faz parte do estabelecimento.",
            )

        try:
            response = (
                supabase
                .table("tenant_members")
                .insert({
                    "tenant_id": tenant_id,
                    "user_id": profile["id"],
                    "role": payload.role,
                    "active": True,
                })
                .execute()
            )
        except Exception:
            response = (
                supabase
                .table("tenant_members")
                .insert({
                    "tenant_id": tenant_id,
                    "user_id": profile["id"],
                    "role": payload.role,
                })
                .execute()
            )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível adicionar membro.",
            )

        member = response.data[0]

        write_audit_log(
            tenant_id=tenant_id,
            action="tenant.member_add",
            entity_type="tenant_member",
            entity_id=member.get("id"),
            description=f"Membro adicionado: {payload.email}",
            metadata={
                "member": member,
                "email": payload.email,
                "role": payload.role,
            },
            current_user=current_user,
            request=request,
        )

        return {
            "member": member,
            "profile": profile,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.get("/subscriptions")
def list_subscriptions(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("subscriptions")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.patch("/subscriptions/{subscription_id}/status")
def update_subscription_status(
    subscription_id: str,
    payload: SubscriptionStatusUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("subscriptions")
            .select("*")
            .eq("id", subscription_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada.",
            )

        old_subscription = old_response.data[0]

        response = (
            supabase
            .table("subscriptions")
            .update({"status": payload.status})
            .eq("id", subscription_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar assinatura.",
            )

        subscription = response.data[0]

        write_audit_log(
            tenant_id=subscription.get("tenant_id"),
            action="subscription.status_update",
            entity_type="subscription",
            entity_id=subscription_id,
            description=f"Status da assinatura alterado para {payload.status}",
            metadata={
                "before": old_subscription,
                "after": subscription,
            },
            current_user=current_user,
            request=request,
        )

        return subscription

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.get("/coupons")
def list_coupons(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("coupons")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.post("/coupons")
def create_coupon(
    payload: CouponCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        code = payload.code.strip().upper()

        existing = (
            supabase
            .table("coupons")
            .select("id")
            .eq("code", code)
            .limit(1)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe um cupom com este código.",
            )

        response = (
            supabase
            .table("coupons")
            .insert({
                "code": code,
                "description": payload.description,
                "discount_type": payload.discount_type,
                "discount_value": payload.discount_value,
                "max_redemptions": payload.max_redemptions,
                "active": payload.active,
            })
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar cupom.",
            )

        coupon = response.data[0]

        write_audit_log(
            action="coupon.create",
            entity_type="coupon",
            entity_id=coupon.get("id"),
            description=f"Cupom criado: {coupon.get('code')}",
            metadata={"coupon": coupon},
            current_user=current_user,
            request=request,
        )

        return coupon

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/coupons/{coupon_id}")
def update_coupon(
    coupon_id: str,
    payload: CouponUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("coupons")
            .select("*")
            .eq("id", coupon_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cupom não encontrado.",
            )

        old_coupon = old_response.data[0]

        update_data = normalize_coupon_payload(payload.model_dump(exclude_unset=True))

        if "code" in update_data and update_data["code"]:
            update_data["code"] = update_data["code"].strip().upper()

            existing = (
                supabase
                .table("coupons")
                .select("id")
                .eq("code", update_data["code"])
                .neq("id", coupon_id)
                .limit(1)
                .execute()
            )

            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Já existe outro cupom com este código.",
                )

        response = (
            supabase
            .table("coupons")
            .update(update_data)
            .eq("id", coupon_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar cupom.",
            )

        coupon = response.data[0]

        write_audit_log(
            action="coupon.update",
            entity_type="coupon",
            entity_id=coupon_id,
            description=f"Cupom atualizado: {coupon.get('code')}",
            metadata={
                "before": old_coupon,
                "changes": update_data,
                "after": coupon,
            },
            current_user=current_user,
            request=request,
        )

        return coupon

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.delete("/coupons/{coupon_id}")
def disable_coupon(
    coupon_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("coupons")
            .select("*")
            .eq("id", coupon_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cupom não encontrado.",
            )

        old_coupon = old_response.data[0]

        response = (
            supabase
            .table("coupons")
            .update({"active": False})
            .eq("id", coupon_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível desativar cupom.",
            )

        coupon = response.data[0]

        write_audit_log(
            action="coupon.disable",
            entity_type="coupon",
            entity_id=coupon_id,
            description=f"Cupom desativado: {old_coupon.get('code')}",
            metadata={
                "before": old_coupon,
                "after": coupon,
            },
            current_user=current_user,
            request=request,
        )

        return coupon

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.get("/asaas-events")
def list_asaas_events(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("asaas_events")
            .select("*")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        return response.data or []

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )