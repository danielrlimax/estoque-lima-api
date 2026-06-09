from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.sale import SaleCreate, SaleResponse

router = APIRouter(prefix="/sales", tags=["Sales"])


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        items = [
            {
                "product_id": item.product_id,
                "quantity": float(item.quantity),
            }
            for item in payload.items
        ]

        response = (
            supabase
            .rpc(
                "create_sale",
                {
                    "p_tenant_id": payload.tenant_id,
                    "p_items": items,
                    "p_payment_method": payload.payment_method,
                    "p_discount": float(payload.discount),
                    "p_customer_name": payload.customer_name,
                    "p_notes": payload.notes,
                },
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar a venda.",
            )

        return {
            "sale_id": str(response.data["sale_id"]),
            "subtotal": Decimal(str(response.data["subtotal"])),
            "discount": Decimal(str(response.data["discount"])),
            "total": Decimal(str(response.data["total"])),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("")
def list_sales(
    tenant_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("sales")
            .select(
                "id, tenant_id, status, payment_method, subtotal, discount, "
                "total, customer_name, notes, created_by, created_at"
            )
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return response.data

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/{sale_id}")
def get_sale(
    sale_id: str,
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        sale_response = (
            supabase
            .table("sales")
            .select(
                "id, tenant_id, status, payment_method, subtotal, discount, "
                "total, customer_name, notes, created_by, created_at"
            )
            .eq("id", sale_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )

        if not sale_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venda não encontrada.",
            )

        items_response = (
            supabase
            .table("sale_items")
            .select(
                "id, product_id, product_name, barcode, quantity, unit_price, total, created_at"
            )
            .eq("sale_id", sale_id)
            .eq("tenant_id", tenant_id)
            .order("created_at")
            .execute()
        )

        return {
            "sale": sale_response.data[0],
            "items": items_response.data,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))