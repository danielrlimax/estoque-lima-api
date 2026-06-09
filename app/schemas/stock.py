from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


StockMovementType = Literal["in", "out", "adjustment"]


class StockAdjustCreate(BaseModel):
    tenant_id: str
    product_id: str
    type: StockMovementType
    quantity: Decimal = Field(gt=0)
    reason: str | None = None


class StockAdjustResponse(BaseModel):
    product_id: str
    previous_stock: Decimal
    new_stock: Decimal