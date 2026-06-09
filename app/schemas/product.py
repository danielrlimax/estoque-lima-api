from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


ProductUnit = Literal["unit", "kg", "g", "l", "ml", "box", "pack"]


class ProductCreate(BaseModel):
    tenant_id: str
    category_id: str | None = None

    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    sku: str | None = None
    barcode: str | None = None

    unit: ProductUnit = "unit"
    sale_price: Decimal = Field(ge=0)
    cost_price: Decimal = Field(default=0, ge=0)

    current_stock: Decimal = Field(default=0, ge=0)
    min_stock: Decimal = Field(default=0, ge=0)

    image_url: str | None = None
    active: bool = True


class ProductUpdate(BaseModel):
    category_id: str | None = None

    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    sku: str | None = None
    barcode: str | None = None

    unit: ProductUnit | None = None
    sale_price: Decimal | None = Field(default=None, ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)

    current_stock: Decimal | None = Field(default=None, ge=0)
    min_stock: Decimal | None = Field(default=None, ge=0)

    image_url: str | None = None
    active: bool | None = None


class ProductResponse(BaseModel):
    id: str
    tenant_id: str
    category_id: str | None = None

    name: str
    description: str | None = None
    sku: str | None = None
    barcode: str | None = None

    unit: str
    sale_price: Decimal
    cost_price: Decimal
    current_stock: Decimal
    min_stock: Decimal

    image_url: str | None = None
    active: bool