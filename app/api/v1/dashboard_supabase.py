from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

        products_response = (
            supabase
            .table("products")
            .select("id, active, current_stock, min_stock")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        sales_response = (
            supabase
            .table("sales")
            .select("id, total, created_at")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        products = products_response.data or []
        sales = sales_response.data or []

        today = datetime.now(timezone.utc).date()
        current_month = datetime.now(timezone.utc).month
        current_year = datetime.now(timezone.utc).year

        sales_today = []
        revenue_today = 0
        revenue_month = 0

        for sale in sales:
            created_at = datetime.fromisoformat(
                sale["created_at"].replace("Z", "+00:00")
            )

            total = float(sale["total"] or 0)

            if created_at.date() == today:
                sales_today.append(sale)
                revenue_today += total

            if created_at.month == current_month and created_at.year == current_year:
                revenue_month += total

        low_stock_products = [
            product
            for product in products
            if product["active"]
            and float(product["current_stock"]) <= float(product["min_stock"])
        ]

        return {
            "total_products": len(products),
            "active_products": len([product for product in products if product["active"]]),
            "low_stock_products": len(low_stock_products),
            "total_sales": len(sales),
            "sales_today": len(sales_today),
            "revenue_today": str(revenue_today),
            "revenue_month": str(revenue_month),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/low-stock")
def get_low_stock_products(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("products")
            .select("id, name, barcode, current_stock, min_stock, sale_price")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .execute()
        )

        products = response.data or []

        low_stock = [
            product
            for product in products
            if float(product["current_stock"]) <= float(product["min_stock"])
        ]

        return low_stock

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/recent-sales")
def get_recent_sales(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("sales")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(10)
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