from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.coupon import CouponValidateRequest, CouponValidateResponse

router = APIRouter(prefix="/coupons", tags=["Coupons"])


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_datetime(value: str | None):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


@router.post("/validate", response_model=CouponValidateResponse)
def validate_coupon(
    payload: CouponValidateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        code = payload.code.strip().upper()
        amount = money(payload.amount)

        response = (
            supabase
            .table("coupons")
            .select(
                "id, code, description, type, value, active, max_uses, "
                "used_count, valid_from, valid_until"
            )
            .eq("code", code)
            .limit(1)
            .execute()
        )

        if not response.data:
            return {
                "valid": False,
                "code": code,
                "type": None,
                "value": None,
                "discount_amount": Decimal("0"),
                "final_amount": amount,
                "message": "Cupom não encontrado.",
            }

        coupon = response.data[0]

        if not coupon["active"]:
            return {
                "valid": False,
                "code": code,
                "type": coupon["type"],
                "value": Decimal(str(coupon["value"])),
                "discount_amount": Decimal("0"),
                "final_amount": amount,
                "message": "Cupom inativo.",
            }

        now = datetime.now(timezone.utc)
        valid_from = parse_datetime(coupon.get("valid_from"))
        valid_until = parse_datetime(coupon.get("valid_until"))

        if valid_from and valid_from > now:
            return {
                "valid": False,
                "code": code,
                "type": coupon["type"],
                "value": Decimal(str(coupon["value"])),
                "discount_amount": Decimal("0"),
                "final_amount": amount,
                "message": "Cupom ainda não está válido.",
            }

        if valid_until and valid_until < now:
            return {
                "valid": False,
                "code": code,
                "type": coupon["type"],
                "value": Decimal(str(coupon["value"])),
                "discount_amount": Decimal("0"),
                "final_amount": amount,
                "message": "Cupom expirado.",
            }

        max_uses = coupon.get("max_uses")
        used_count = coupon.get("used_count") or 0

        if max_uses is not None and used_count >= max_uses:
            return {
                "valid": False,
                "code": code,
                "type": coupon["type"],
                "value": Decimal(str(coupon["value"])),
                "discount_amount": Decimal("0"),
                "final_amount": amount,
                "message": "Cupom atingiu o limite de uso.",
            }

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

        return {
            "valid": True,
            "code": code,
            "type": coupon_type,
            "value": coupon_value,
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "message": "Cupom válido.",
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )