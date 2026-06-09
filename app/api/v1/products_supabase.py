from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])


def decimal_to_float(value):
    if isinstance(value, Decimal):
        return float(value)

    return value


def normalize_product_payload(data: dict) -> dict:
    output = {}

    for key, value in data.items():
        if isinstance(value, Decimal):
            output[key] = float(value)
        else:
            output[key] = value

    return output


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        data = normalize_product_payload(payload.model_dump())

        response = (
            supabase
            .table("products")
            .insert(data)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar o produto.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("", response_model=list[ProductResponse])
def list_products(
    tenant_id: str = Query(...),
    search: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        query = (
            supabase
            .table("products")
            .select(
                "id, tenant_id, category_id, name, description, sku, barcode, "
                "unit, sale_price, cost_price, current_stock, min_stock, "
                "image_url, active"
            )
            .eq("tenant_id", tenant_id)
            .order("name")
        )

        if search:
            query = query.or_(
                f"name.ilike.%{search}%,barcode.ilike.%{search}%,sku.ilike.%{search}%"
            )

        response = query.execute()

        return response.data

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/barcode/{barcode}", response_model=ProductResponse)
def get_product_by_barcode(
    barcode: str,
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("products")
            .select(
                "id, tenant_id, category_id, name, description, sku, barcode, "
                "unit, sale_price, cost_price, current_stock, min_stock, "
                "image_url, active"
            )
            .eq("tenant_id", tenant_id)
            .eq("barcode", barcode)
            .eq("active", True)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado para este código de barras.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        data = payload.model_dump(exclude_unset=True)
        data = normalize_product_payload(data)

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum campo enviado para atualização.",
            )

        response = (
            supabase
            .table("products")
            .update(data)
            .eq("id", product_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))