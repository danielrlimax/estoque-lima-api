from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.core.tenant_security import ensure_safe_tenant_access
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


@router.get("/summary")
def dashboard_summary(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_access(current_user, tenant_id)
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

        products_response = (
            supabase
            .table("products")
            .select("id,current_stock,min_stock,active")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        sales_response = (
            supabase
            .table("sales")
            .select("id,total,status,created_at")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        products = products_response.data or []
        sales = sales_response.data or []

        active_products = [
            product
            for product in products
            if product.get("active") is True
        ]

        low_stock_products = [
            product
            for product in active_products
            if to_decimal(product.get("current_stock")) <= to_decimal(product.get("min_stock"))
        ]

        completed_sales = [
            sale
            for sale in sales
            if sale.get("status") == "completed"
        ]

        total_revenue = sum(
            to_decimal(sale.get("total"))
            for sale in completed_sales
        )

        return {
            "total_products": len(products),
            "active_products": len(active_products),
            "low_stock_products": len(low_stock_products),
            "total_sales": len(completed_sales),
            "total_revenue": str(total_revenue),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/low-stock")
def dashboard_low_stock(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_access(current_user, tenant_id)
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("products")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .execute()
        )

        products = response.data or []

        low_stock = [
            product
            for product in products
            if to_decimal(product.get("current_stock")) <= to_decimal(product.get("min_stock"))
        ]

        return low_stock[:10]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/recent-sales")
def dashboard_recent_sales(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_access(current_user, tenant_id)
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

        response = (
            supabase
            .table("sales")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(8)
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