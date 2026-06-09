from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


PaymentMethod = Literal[
    "cash",
    "pix",
    "card",
    "credit",
    "debit",
    "external",
    "pending",
]


class SaleItemCreate(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class SaleCreate(BaseModel):
    tenant_id: str
    items: list[SaleItemCreate] = Field(min_length=1)
    payment_method: PaymentMethod = "cash"
    discount: Decimal = Field(default=0, ge=0)
    customer_name: str | None = None
    notes: str | None = None


class SaleResponse(BaseModel):
    sale_id: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal