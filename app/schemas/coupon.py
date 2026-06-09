from decimal import Decimal

from pydantic import BaseModel, Field


class CouponValidateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    amount: Decimal = Field(gt=0)


class CouponValidateResponse(BaseModel):
    valid: bool
    code: str
    type: str | None = None
    value: Decimal | None = None
    discount_amount: Decimal = Decimal("0")
    final_amount: Decimal
    message: str