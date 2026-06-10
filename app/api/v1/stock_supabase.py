from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/stock", tags=["Stock"])


class StockAdjustRequest(BaseModel):
    tenant_id: str
    product_id: str
    type: str
    quantity: Decimal = Field(gt=0)
    reason: str | None = None


def validate_movement_type(value: str):
    allowed = {"in", "out", "adjustment"}

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de movimentação inválido.",
        )


@router.post("/adjust")
def adjust_stock(
    payload: StockAdjustRequest,
    current_user: dict = Depends(get_current_user),
):
    validate_movement_type(payload.type)
    ensure_tenant_access_is_active(payload.tenant_id)

    try:
        supabase = get_supabase_admin()

        product_response = (
            supabase
            .table("products")
            .select("id, tenant_id, current_stock")
            .eq("id", payload.product_id)
            .eq("tenant_id", payload.tenant_id)
            .limit(1)
            .execute()
        )

        if not product_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado.",
            )

        product = product_response.data[0]
        current_stock = Decimal(str(product["current_stock"]))
        quantity = payload.quantity

        if payload.type == "in":
            new_stock = current_stock + quantity
        elif payload.type == "out":
            if quantity > current_stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Estoque insuficiente para saída.",
                )

            new_stock = current_stock - quantity
        else:
            new_stock = quantity

        product_update_response = (
            supabase
            .table("products")
            .update({"current_stock": str(new_stock)})
            .eq("id", payload.product_id)
            .eq("tenant_id", payload.tenant_id)
            .execute()
        )

        if not product_update_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar estoque.",
            )

        movement_response = (
            supabase
            .table("stock_movements")
            .insert({
                "tenant_id": payload.tenant_id,
                "product_id": payload.product_id,
                "type": payload.type,
                "quantity": str(quantity),
                "previous_stock": str(current_stock),
                "new_stock": str(new_stock),
                "reason": payload.reason,
                "created_by": current_user.get("id"),
            })
            .execute()
        )

        return {
            "product": product_update_response.data[0],
            "movement": movement_response.data[0] if movement_response.data else None,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )