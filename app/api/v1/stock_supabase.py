from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.stock import StockAdjustCreate, StockAdjustResponse

router = APIRouter(prefix="/stock", tags=["Stock"])


@router.post("/adjust", response_model=StockAdjustResponse)
def adjust_stock(
    payload: StockAdjustCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .rpc(
                "adjust_stock",
                {
                    "p_tenant_id": payload.tenant_id,
                    "p_product_id": payload.product_id,
                    "p_type": payload.type,
                    "p_quantity": float(payload.quantity),
                    "p_reason": payload.reason,
                },
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível ajustar o estoque.",
            )

        return {
            "product_id": str(response.data["product_id"]),
            "previous_stock": Decimal(str(response.data["previous_stock"])),
            "new_stock": Decimal(str(response.data["new_stock"])),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))