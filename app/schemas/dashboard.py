from decimal import Decimal

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    tenant_id: str
    total_products: int
    active_products: int
    low_stock_products: int
    total_stock_units: Decimal
    total_stock_cost_value: Decimal
    total_stock_sale_value: Decimal
    total_sales_count: int
    total_sales_value: Decimal


class LowStockProductResponse(BaseModel):
    id: str
    name: str
    barcode: str | None = None
    current_stock: Decimal
    min_stock: Decimal
    sale_price: Decimal
    active: bool


class RecentSaleResponse(BaseModel):
    id: str
    status: str
    payment_method: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    customer_name: str | None = None
    created_at: str