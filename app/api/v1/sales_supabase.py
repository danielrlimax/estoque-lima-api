from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.audit import write_audit_log
from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.core.tenant_security import (
    ensure_safe_tenant_access,
    ensure_safe_tenant_management,
)
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/sales", tags=["Sales"])


class SaleItemRequest(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class SaleCreateRequest(BaseModel):
    tenant_id: str
    items: list[SaleItemRequest] = Field(min_length=1)
    payment_method: str
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    customer_name: str | None = None
    notes: str | None = None


@router.get("")
def list_sales(
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
            .limit(50)
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


def create_sale_row(
    *,
    tenant_id: str,
    customer_name: str | None,
    payment_method: str,
    subtotal: Decimal,
    discount: Decimal,
    total: Decimal,
    notes: str | None,
    created_by: str | None,
) -> dict:
    supabase = get_supabase_admin()

    base_payload = {
        "tenant_id": tenant_id,
        "customer_name": customer_name,
        "payment_method": payment_method,
        "subtotal": str(subtotal),
        "discount": str(discount),
        "total": str(total),
        "notes": notes,
        "created_by": created_by,
    }

    # Status principal da nossa regra de negócio.
    # Se o enum do banco ainda não tiver "completed", rode:
    # alter type public.sale_status add value if not exists 'completed';
    try:
        response = (
            supabase
            .table("sales")
            .insert({
                **base_payload,
                "status": "completed",
            })
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception as error:
        error_text = str(error)

        if "sale_status" not in error_text and "status" not in error_text:
            raise

    # Fallback para bancos com default em sales.status.
    try:
        response = (
            supabase
            .table("sales")
            .insert(base_payload)
            .execute()
        )

        if response.data:
            return response.data[0]

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Não foi possível criar venda.",
    )


@router.post("")
def create_sale(
    payload: SaleCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_management(current_user, payload.tenant_id)
    ensure_tenant_access_is_active(payload.tenant_id)

    try:
        supabase = get_supabase_admin()

        product_ids = [item.product_id for item in payload.items]

        products_response = (
            supabase
            .table("products")
            .select("*")
            .in_("id", product_ids)
            .execute()
        )

        products = products_response.data or []

        if len(products) != len(set(product_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Um ou mais produtos da venda não foram encontrados.",
            )

        products_by_id = {
            product["id"]: product
            for product in products
        }

        subtotal = Decimal("0")
        sale_items_to_insert = []
        product_updates = []

        for item in payload.items:
            product = products_by_id.get(item.product_id)

            if not product:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Produto não encontrado.",
                )

            if product.get("tenant_id") != payload.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="A venda contém produto de outro estabelecimento.",
                )

            if not product.get("active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Produto inativo: {product.get('name')}",
                )

            current_stock = Decimal(str(product.get("current_stock") or 0))
            quantity = Decimal(str(item.quantity))

            if quantity > current_stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Estoque insuficiente para {product.get('name')}.",
                )

            unit_price = Decimal(str(product.get("sale_price") or 0))
            total_price = unit_price * quantity

            subtotal += total_price

            sale_items_to_insert.append({
                "tenant_id": payload.tenant_id,
                "product_id": item.product_id,
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "total_price": str(total_price),
            })

            product_updates.append({
                "product_id": item.product_id,
                "old_stock": current_stock,
                "new_stock": current_stock - quantity,
                "quantity": quantity,
                "product_name": product.get("name"),
            })

        discount = Decimal(str(payload.discount or 0))

        if discount > subtotal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Desconto não pode ser maior que o subtotal.",
            )

        total = subtotal - discount

        customer_name = (
            payload.customer_name.strip()
            if payload.customer_name and payload.customer_name.strip()
            else None
        )

        sale = create_sale_row(
            tenant_id=payload.tenant_id,
            customer_name=customer_name,
            payment_method=payload.payment_method,
            subtotal=subtotal,
            discount=discount,
            total=total,
            notes=payload.notes,
            created_by=current_user.get("id"),
        )

        sale_id = sale["id"]

        items_with_sale_id = [
            {
                **item,
                "sale_id": sale_id,
            }
            for item in sale_items_to_insert
        ]

        items_response = (
            supabase
            .table("sale_items")
            .insert(items_with_sale_id)
            .execute()
        )

        for update in product_updates:
            supabase.table("products").update({
                "current_stock": str(update["new_stock"]),
            }).eq("id", update["product_id"]).execute()

            supabase.table("stock_movements").insert({
                "tenant_id": payload.tenant_id,
                "product_id": update["product_id"],
                "movement_type": "out",
                "quantity": str(update["quantity"]),
                "previous_stock": str(update["old_stock"]),
                "new_stock": str(update["new_stock"]),
                "reason": f"Venda {sale_id}",
                "created_by": current_user.get("id"),
            }).execute()

        write_audit_log(
            tenant_id=payload.tenant_id,
            action="sale.create",
            entity_type="sale",
            entity_id=sale_id,
            description=f"Venda finalizada: {str(total)}",
            metadata={
                "sale": sale,
                "items": items_with_sale_id,
                "stock_updates": [
                    {
                        "product_id": update["product_id"],
                        "product_name": update["product_name"],
                        "old_stock": str(update["old_stock"]),
                        "new_stock": str(update["new_stock"]),
                    }
                    for update in product_updates
                ],
            },
            current_user=current_user,
            request=request,
        )

        return {
            "sale": sale,
            "items": items_response.data or [],
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )