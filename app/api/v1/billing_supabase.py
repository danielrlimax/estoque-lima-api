from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.config import settings
from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_admin, get_supabase_with_token
from app.schemas.billing import StartSubscriptionRequest, StartSubscriptionResponse
from app.services.asaas_service import AsaasService

router = APIRouter(prefix="/billing", tags=["Billing"])


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_coupon_discount(coupon: dict, amount: Decimal) -> tuple[Decimal, Decimal]:
    coupon_type = coupon["type"]
    coupon_value = Decimal(str(coupon["value"]))

    if coupon_type == "percentage":
        discount_amount = money(amount * coupon_value / Decimal("100"))
    elif coupon_type == "fixed":
        discount_amount = money(coupon_value)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de cupom inválido.",
        )

    if discount_amount > amount:
        discount_amount = amount

    final_amount = money(amount - discount_amount)

    return discount_amount, final_amount


def validate_coupon_data(coupon: dict) -> None:
    now = datetime.now(timezone.utc)

    if not coupon["active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cupom inativo.",
        )

    if coupon.get("valid_from"):
        valid_from = datetime.fromisoformat(coupon["valid_from"].replace("Z", "+00:00"))
        if valid_from > now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cupom ainda não está válido.",
            )

    if coupon.get("valid_until"):
        valid_until = datetime.fromisoformat(coupon["valid_until"].replace("Z", "+00:00"))
        if valid_until < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cupom expirado.",
            )

    max_uses = coupon.get("max_uses")
    used_count = coupon.get("used_count") or 0

    if max_uses is not None and used_count >= max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cupom atingiu o limite de uso.",
        )


@router.post("/start-subscription", response_model=StartSubscriptionResponse)
async def start_subscription(
    payload: StartSubscriptionRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        member_response = (
            supabase
            .table("tenant_members")
            .select("role")
            .eq("tenant_id", payload.tenant_id)
            .eq("user_id", current_user["id"])
            .eq("active", True)
            .in_("role", ["owner", "admin"])
            .limit(1)
            .execute()
        )

        if not member_response.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas owner ou admin pode iniciar assinatura.",
            )

        plan_response = (
            supabase
            .table("plans")
            .select("id, code, name, price_monthly")
            .eq("code", "starter")
            .limit(1)
            .execute()
        )

        if not plan_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plano starter não encontrado.",
            )

        plan = plan_response.data[0]
        original_price = money(Decimal(str(plan["price_monthly"])))

        if original_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O plano starter está com preço zerado. Configure um valor antes de criar assinatura no Asaas.",
            )

        discount_amount = Decimal("0.00")
        final_price = original_price
        coupon = None
        coupon_code = None

        if payload.coupon_code:
            coupon_code = payload.coupon_code.strip().upper()

            coupon_response = (
                supabase
                .table("coupons")
                .select(
                    "id, code, type, value, active, max_uses, used_count, "
                    "valid_from, valid_until"
                )
                .eq("code", coupon_code)
                .limit(1)
                .execute()
            )

            if not coupon_response.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cupom não encontrado.",
                )

            coupon = coupon_response.data[0]
            validate_coupon_data(coupon)
            discount_amount, final_price = calculate_coupon_discount(coupon, original_price)

        if final_price <= 0:
            final_price = Decimal("0.01")

        asaas = AsaasService()

        customer = await asaas.create_customer(
            name=payload.customer_name,
            email=payload.customer_email,
            cpf_cnpj=payload.cpf_cnpj,
            phone=payload.phone,
        )

        subscription = await asaas.create_subscription(
            customer_id=customer["id"],
            value=float(final_price),
            billing_type=payload.billing_type,
            cycle="MONTHLY",
            description=f"Assinatura {plan['name']} - Estoque SaaS",
        )

        metadata = {
            "asaas_customer": customer,
            "asaas_subscription": subscription,
            "billing": {
                "original_price": float(original_price),
                "discount_amount": float(discount_amount),
                "final_price": float(final_price),
                "coupon_code": coupon_code,
            },
        }

        update_response = (
            supabase
            .table("subscriptions")
            .update({
                "provider": "asaas",
                "asaas_customer_id": customer["id"],
                "asaas_subscription_id": subscription["id"],
                "status": "active",
                "metadata": metadata,
            })
            .eq("tenant_id", payload.tenant_id)
            .execute()
        )

        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assinatura criada no Asaas, mas não foi possível atualizar no Supabase.",
            )

        if coupon:
            supabase.table("coupons").update({
                "used_count": (coupon.get("used_count") or 0) + 1,
            }).eq("id", coupon["id"]).execute()

            supabase.table("tenant_coupons").insert({
                "tenant_id": payload.tenant_id,
                "coupon_id": coupon["id"],
                "applied_by": current_user["id"],
            }).execute()

        return {
            "tenant_id": payload.tenant_id,
            "asaas_customer_id": customer["id"],
            "asaas_subscription_id": subscription["id"],
            "status": update_response.data[0]["status"],
            "original_price": float(original_price),
            "discount_amount": float(discount_amount),
            "final_price": float(final_price),
            "coupon_code": coupon_code,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.post("/asaas/webhook")
async def asaas_webhook(
    request: Request,
    asaas_access_token: str | None = Header(default=None, alias="asaas-access-token"),
):
    expected_token = settings.ASAAS_WEBHOOK_TOKEN.strip()
    received_token = (asaas_access_token or "").strip()

    if expected_token != "troque_esse_token":
        if received_token != expected_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook não autorizado.",
            )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload inválido.",
        )

    event_type = payload.get("event")
    payment = payload.get("payment") or {}

    payment_id = payment.get("id")
    subscription_id = payment.get("subscription")
    customer_id = payment.get("customer")

    supabase = get_supabase_admin()

    try:
        event_insert = (
            supabase
            .table("asaas_events")
            .insert({
                "event_id": payload.get("id"),
                "event_type": event_type,
                "payment_id": payment_id,
                "subscription_id": subscription_id,
                "customer_id": customer_id,
                "payload": payload,
                "processed": False,
            })
            .execute()
        )

        new_status = None

        if event_type in ["PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"]:
            new_status = "active"

        elif event_type == "PAYMENT_OVERDUE":
            new_status = "past_due"

        elif event_type in ["PAYMENT_DELETED", "PAYMENT_REFUNDED"]:
            new_status = "canceled"

        elif event_type == "PAYMENT_RESTORED":
            new_status = "active"

        if subscription_id and new_status:
            supabase.table("subscriptions").update({
                "status": new_status,
                "metadata": {
                    "last_asaas_event": payload,
                },
            }).eq("asaas_subscription_id", subscription_id).execute()

        if event_insert.data:
            event_row_id = event_insert.data[0]["id"]

            supabase.table("asaas_events").update({
                "processed": True,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", event_row_id).execute()

        return {
            "received": True,
            "event": event_type,
            "processed_status": new_status,
        }

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )