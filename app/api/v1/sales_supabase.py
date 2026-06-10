from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.audit import write_audit_log
from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/sales", tags=["Sales"])


class SaleItemRequest(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class SaleCreateRequest(BaseModel):
    tenant_id: str
    items: list[SaleItemRequest]
    payment_method: str
    discount: Decimal = Field(default=0, ge=0)
    customer_name: str | None = None
    notes: str | None = None


def validate_payment_method(value: str):
    allowed = {"cash", "pix", "credit_card", "debit_card"}

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Forma de pagamento inválida.",
        )


@router.get("")
def list_sales(
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
            .limit(100)
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


@router.get("/{sale_id}")
def get_sale(
    sale_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_admin()

        sale_response = (
            supabase
            .table("sales")
            .select("*")
            .eq("id", sale_id)
            .limit(1)
            .execute()
        )

        if not sale_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venda não encontrada.",
            )

        sale = sale_response.data[0]

        ensure_tenant_access_is_active(sale["tenant_id"])

        items_response = (
            supabase
            .table("sale_items")
            .select("*")
            .eq("sale_id", sale_id)
            .execute()
        )

        return {
            **sale,
            "items": items_response.data or [],
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.post("")
def create_sale(
    payload: SaleCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    validate_payment_method(payload.payment_method)
    ensure_tenant_access_is_active(payload.tenant_id)

    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A venda precisa ter pelo menos um item.",
        )

    try:
        supabase = get_supabase_admin()

        product_ids = [item.product_id for item in payload.items]

        products_response = (
            supabase
            .table("products")
            .select("id, tenant_id, name, sale_price, current_stock, active")
            .in_("id", product_ids)
            .eq("tenant_id", payload.tenant_id)
            .execute()
        )

        products = products_response.data or []
        products_by_id = {product["id"]: product for product in products}

        if len(products_by_id) != len(set(product_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Um ou mais produtos não foram encontrados.",
            )

        subtotal = Decimal("0")
        sale_items_to_insert = []
        stock_updates = []

        for item in payload.items:
            product = products_by_id[item.product_id]

            if not product.get("active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Produto inativo: {product['name']}",
                )

            current_stock = Decimal(str(product["current_stock"]))
            quantity = item.quantity

            if quantity > current_stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Estoque insuficiente para o produto {product['name']}.",
                )

            unit_price = Decimal(str(product["sale_price"]))
            item_total = unit_price * quantity
            subtotal += item_total

            new_stock = current_stock - quantity

            sale_items_to_insert.append({
                "tenant_id": payload.tenant_id,
                "product_id": product["id"],
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "total": str(item_total),
            })

            stock_updates.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "previous_stock": str(current_stock),
                "new_stock": str(new_stock),
                "quantity": str(quantity),
            })

        discount = payload.discount

        if discount > subtotal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Desconto não pode ser maior que o subtotal.",
            )

        total = subtotal - discount

        sale_response = (
            supabase
            .table("sales")
            .insert({
                "tenant_id": payload.tenant_id,
                "customer_name": payload.customer_name,
                "payment_method": payload.payment_method,
                "subtotal": str(subtotal),
                "discount": str(discount),
                "total": str(total),
                "status": "completed",
                "notes": payload.notes,
                "created_by": current_user.get("id"),
            })
            .execute()
        )

        if not sale_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar venda.",
            )

        sale = sale_response.data[0]

        sale_items_with_sale_id = [
            {
                **item,
                "sale_id": sale["id"],
            }
            for item in sale_items_to_insert
        ]

        items_response = (
            supabase
            .table("sale_items")
            .insert(sale_items_with_sale_id)
            .execute()
        )

        for stock_update in stock_updates:
            supabase.table("products").update({
                "current_stock": stock_update["new_stock"],
            }).eq("id", stock_update["product_id"]).eq(
                "tenant_id", payload.tenant_id
            ).execute()

            supabase.table("stock_movements").insert({
                "tenant_id": payload.tenant_id,
                "product_id": stock_update["product_id"],
                "type": "out",
                "quantity": stock_update["quantity"],
                "previous_stock": stock_update["previous_stock"],
                "new_stock": stock_update["new_stock"],
                "reason": f"Venda #{sale['id']}",
                "created_by": current_user.get("id"),
            }).execute()

        write_audit_log(
            action="sale.create",
            entity_type="sale",
            tenant_id=payload.tenant_id,
            entity_id=sale["id"],
            description=f"Venda finalizada no valor de R$ {total}.",
            metadata={
                "sale_id": sale["id"],
                "payment_method": payload.payment_method,
                "customer_name": payload.customer_name,
                "subtotal": str(subtotal),
                "discount": str(discount),
                "total": str(total),
                "items": sale_items_with_sale_id,
                "stock_updates": stock_updates,
            },
            current_user=current_user,
            request=request,
        )

        return {
            **sale,
            "items": items_response.data or [],
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )