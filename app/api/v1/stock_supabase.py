from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.audit import write_audit_log
from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.core.tenant_security import ensure_safe_tenant_management
from app.db.supabase_client import get_supabase_admin

router = APIRouter(prefix="/stock", tags=["Stock"])


class StockAdjustRequest(BaseModel):
    tenant_id: str
    product_id: str
    quantity: Decimal
    movement_type: str = Field(pattern="^(in|out|adjustment)$")
    reason: str | None = None


@router.post("/adjust")
def adjust_stock(
    payload: StockAdjustRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_management(current_user, payload.tenant_id)
    ensure_tenant_access_is_active(payload.tenant_id)

    try:
        supabase = get_supabase_admin()

        product_response = (
            supabase
            .table("products")
            .select("*")
            .eq("id", payload.product_id)
            .limit(1)
            .execute()
        )

        if not product_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado.",
            )

        product = product_response.data[0]

        if product.get("tenant_id") != payload.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Produto não pertence a este estabelecimento.",
            )

        current_stock = Decimal(str(product.get("current_stock") or 0))
        quantity = Decimal(str(payload.quantity))

        if payload.movement_type == "in":
            new_stock = current_stock + quantity
        elif payload.movement_type == "out":
            new_stock = current_stock - quantity
        else:
            new_stock = quantity

        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Estoque não pode ficar negativo.",
            )

        updated_response = (
            supabase
            .table("products")
            .update({"current_stock": str(new_stock)})
            .eq("id", payload.product_id)
            .execute()
        )

        if not updated_response.data:
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
                "movement_type": payload.movement_type,
                "quantity": str(quantity),
                "previous_stock": str(current_stock),
                "new_stock": str(new_stock),
                "reason": payload.reason,
                "created_by": current_user.get("id"),
            })
            .execute()
        )

        movement = movement_response.data[0] if movement_response.data else None

        write_audit_log(
            tenant_id=payload.tenant_id,
            action="stock.adjust",
            entity_type="stock_movement",
            entity_id=movement.get("id") if movement else payload.product_id,
            description=f"Estoque ajustado: {product.get('name')}",
            metadata={
                "product_id": payload.product_id,
                "movement_type": payload.movement_type,
                "quantity": str(quantity),
                "previous_stock": str(current_stock),
                "new_stock": str(new_stock),
            },
            current_user=current_user,
            request=request,
        )

        return {
            "product": updated_response.data[0],
            "movement": movement,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )