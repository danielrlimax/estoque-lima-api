from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    LowStockProductResponse,
    RecentSaleResponse,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def decimal_value(value) -> Decimal:
    if value is None:
        return Decimal("0")

    return Decimal(str(value))


def ensure_member(
    supabase,
    tenant_id: str,
    user_id: str,
):
    member_response = (
        supabase
        .table("tenant_members")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("user_id", user_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )

    if not member_response.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não pertence a este tenant.",
        )


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])
        ensure_member(supabase, tenant_id, current_user["id"])

        products_response = (
            supabase
            .table("products")
            .select("id, active, current_stock, min_stock, sale_price, cost_price")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        sales_response = (
            supabase
            .table("sales")
            .select("id, total, status")
            .eq("tenant_id", tenant_id)
            .neq("status", "canceled")
            .execute()
        )

        products = products_response.data or []
        sales = sales_response.data or []

        total_products = len(products)
        active_products = 0
        low_stock_products = 0

        total_stock_units = Decimal("0")
        total_stock_cost_value = Decimal("0")
        total_stock_sale_value = Decimal("0")

        for product in products:
            active = bool(product.get("active"))
            current_stock = decimal_value(product.get("current_stock"))
            min_stock = decimal_value(product.get("min_stock"))
            sale_price = decimal_value(product.get("sale_price"))
            cost_price = decimal_value(product.get("cost_price"))

            if active:
                active_products += 1

            if active and current_stock <= min_stock:
                low_stock_products += 1

            total_stock_units += current_stock
            total_stock_cost_value += current_stock * cost_price
            total_stock_sale_value += current_stock * sale_price

        total_sales_value = Decimal("0")

        for sale in sales:
            total_sales_value += decimal_value(sale.get("total"))

        return {
            "tenant_id": tenant_id,
            "total_products": total_products,
            "active_products": active_products,
            "low_stock_products": low_stock_products,
            "total_stock_units": total_stock_units,
            "total_stock_cost_value": money(total_stock_cost_value),
            "total_stock_sale_value": money(total_stock_sale_value),
            "total_sales_count": len(sales),
            "total_sales_value": money(total_sales_value),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/low-stock", response_model=list[LowStockProductResponse])
def get_low_stock_products(
    tenant_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])
        ensure_member(supabase, tenant_id, current_user["id"])

        response = (
            supabase
            .table("products")
            .select("id, name, barcode, current_stock, min_stock, sale_price, active")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .order("current_stock")
            .limit(limit)
            .execute()
        )

        products = response.data or []

        low_stock = []

        for product in products:
            current_stock = decimal_value(product.get("current_stock"))
            min_stock = decimal_value(product.get("min_stock"))

            if current_stock <= min_stock:
                low_stock.append(product)

        return low_stock

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/recent-sales", response_model=list[RecentSaleResponse])
def get_recent_sales(
    tenant_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])
        ensure_member(supabase, tenant_id, current_user["id"])

        response = (
            supabase
            .table("sales")
            .select(
                "id, status, payment_method, subtotal, discount, total, "
                "customer_name, created_at"
            )
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data or []

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )