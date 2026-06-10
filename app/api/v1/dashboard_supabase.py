from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.core.tenant_security import ensure_safe_tenant_access
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def decimal_to_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        normalized = str(value).strip()

        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        parsed = datetime.fromisoformat(normalized)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(APP_TIMEZONE)

    except Exception:
        return None


def is_product_active(product: dict) -> bool:
    if "active" in product:
        return product.get("active") is True

    if "is_active" in product:
        return product.get("is_active") is True

    return True


def is_sale_countable(sale: dict) -> bool:
    """
    Define se uma venda deve entrar no faturamento.

    Motivo:
    - Alguns bancos antigos podem não ter coluna status.
    - Alguns inserts podem criar venda sem status por causa de enum antigo.
    - Para venda de balcão/POS, venda sem status deve contar como concluída.
    """
    raw_status = sale.get("status")

    if raw_status is None:
        return True

    sale_status = str(raw_status).strip().lower()

    if not sale_status:
        return True

    invalid_statuses = {
        "canceled",
        "cancelled",
        "cancelada",
        "refunded",
        "estornada",
        "void",
        "deleted",
    }

    return sale_status not in invalid_statuses


def sale_is_today(sale: dict, now: datetime) -> bool:
    created_at = parse_datetime(sale.get("created_at"))

    if not created_at:
        return False

    return created_at.date() == now.date()


def sale_is_current_month(sale: dict, now: datetime) -> bool:
    created_at = parse_datetime(sale.get("created_at"))

    if not created_at:
        return False

    return created_at.year == now.year and created_at.month == now.month


def get_products_for_dashboard(tenant_id: str) -> list[dict]:
    supabase = get_supabase_admin()

    try:
        response = (
            supabase
            .table("products")
            .select("id,current_stock,min_stock,active,is_active")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return response.data or []

    except Exception:
        response = (
            supabase
            .table("products")
            .select("*")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return response.data or []


def get_sales_for_dashboard(tenant_id: str) -> list[dict]:
    supabase = get_supabase_admin()

    try:
        response = (
            supabase
            .table("sales")
            .select("id,total,subtotal,discount,status,created_at")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return response.data or []

    except Exception:
        response = (
            supabase
            .table("sales")
            .select("*")
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return response.data or []


@router.get("/summary")
def dashboard_summary(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_access(current_user, tenant_id)
    ensure_tenant_access_is_active(tenant_id)

    try:
        products = get_products_for_dashboard(tenant_id)
        sales = get_sales_for_dashboard(tenant_id)

        now = datetime.now(APP_TIMEZONE)

        active_products = [
            product
            for product in products
            if is_product_active(product)
        ]

        low_stock_products = [
            product
            for product in active_products
            if to_decimal(product.get("current_stock")) <= to_decimal(product.get("min_stock"))
        ]

        countable_sales = [
            sale
            for sale in sales
            if is_sale_countable(sale)
        ]

        sales_today = [
            sale
            for sale in countable_sales
            if sale_is_today(sale, now)
        ]

        sales_month = [
            sale
            for sale in countable_sales
            if sale_is_current_month(sale, now)
        ]

        total_revenue = sum(
            to_decimal(sale.get("total"))
            for sale in countable_sales
        )

        revenue_today = sum(
            to_decimal(sale.get("total"))
            for sale in sales_today
        )

        revenue_month = sum(
            to_decimal(sale.get("total"))
            for sale in sales_month
        )

        return {
            "total_products": len(products),
            "active_products": len(active_products),
            "low_stock_products": len(low_stock_products),

            "total_sales": len(countable_sales),
            "sales_today": len(sales_today),

            "total_revenue": decimal_to_string(total_revenue),
            "revenue_today": decimal_to_string(revenue_today),
            "revenue_month": decimal_to_string(revenue_month),
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

        try:
            response = (
                supabase
                .table("products")
                .select("*")
                .eq("tenant_id", tenant_id)
                .eq("active", True)
                .execute()
            )

            products = response.data or []

        except Exception:
            try:
                response = (
                    supabase
                    .table("products")
                    .select("*")
                    .eq("tenant_id", tenant_id)
                    .eq("is_active", True)
                    .execute()
                )

                products = response.data or []

            except Exception:
                response = (
                    supabase
                    .table("products")
                    .select("*")
                    .eq("tenant_id", tenant_id)
                    .execute()
                )

                products = [
                    product
                    for product in response.data or []
                    if is_product_active(product)
                ]

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

        sales = response.data or []

        return [
            sale
            for sale in sales
            if is_sale_countable(sale)
        ]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )