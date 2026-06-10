from decimal import Decimal
from typing import Any

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

router = APIRouter(prefix="/products", tags=["Products"])


class ProductCreateRequest(BaseModel):
    tenant_id: str
    category_id: str | None = None
    name: str = Field(min_length=2, max_length=180)
    description: str | None = None
    barcode: str | None = None
    unit: str = "unit"
    cost_price: Decimal = Field(default=Decimal("0"), ge=0)
    sale_price: Decimal = Field(default=Decimal("0"), ge=0)
    current_stock: Decimal = Field(default=Decimal("0"), ge=0)
    min_stock: Decimal = Field(default=Decimal("0"), ge=0)
    active: bool = True


class ProductUpdateRequest(BaseModel):
    category_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = None
    barcode: str | None = None
    unit: str | None = None
    cost_price: Decimal | None = Field(default=None, ge=0)
    sale_price: Decimal | None = Field(default=None, ge=0)
    current_stock: Decimal | None = Field(default=None, ge=0)
    min_stock: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


def normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
    normalized = {}

    for key, value in data.items():
        if isinstance(value, Decimal):
            normalized[key] = str(value)
        else:
            normalized[key] = value

    return normalized


@router.get("")
def list_products(
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
            .order("created_at", desc=True)
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


@router.get("/barcode/{barcode}")
def get_product_by_barcode(
    barcode: str,
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
            .eq("barcode", barcode)
            .eq("active", True)
            .limit(1)
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.post("")
def create_product(
    payload: ProductCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_management(current_user, payload.tenant_id)
    ensure_tenant_access_is_active(payload.tenant_id)

    try:
        supabase = get_supabase_admin()

        if payload.barcode:
            existing = (
                supabase
                .table("products")
                .select("id")
                .eq("tenant_id", payload.tenant_id)
                .eq("barcode", payload.barcode)
                .limit(1)
                .execute()
            )

            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Já existe um produto com este código de barras.",
                )

        data = normalize_payload(payload.model_dump())

        response = (
            supabase
            .table("products")
            .insert(data)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar produto.",
            )

        product = response.data[0]

        write_audit_log(
            tenant_id=payload.tenant_id,
            action="product.create",
            entity_type="product",
            entity_id=product.get("id"),
            description=f"Produto criado: {product.get('name')}",
            metadata={"product": product},
            current_user=current_user,
            request=request,
        )

        return product

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/{product_id}")
def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("products")
            .select("*")
            .eq("id", product_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado.",
            )

        old_product = old_response.data[0]
        tenant_id = old_product["tenant_id"]

        ensure_safe_tenant_management(current_user, tenant_id)
        ensure_tenant_access_is_active(tenant_id)

        update_data = normalize_payload(payload.model_dump(exclude_unset=True))

        if "barcode" in update_data and update_data["barcode"]:
            existing = (
                supabase
                .table("products")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("barcode", update_data["barcode"])
                .neq("id", product_id)
                .limit(1)
                .execute()
            )

            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Já existe outro produto com este código de barras.",
                )

        response = (
            supabase
            .table("products")
            .update(update_data)
            .eq("id", product_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar produto.",
            )

        product = response.data[0]

        write_audit_log(
            tenant_id=tenant_id,
            action="product.update",
            entity_type="product",
            entity_id=product_id,
            description=f"Produto atualizado: {product.get('name')}",
            metadata={
                "before": old_product,
                "changes": update_data,
                "after": product,
            },
            current_user=current_user,
            request=request,
        )

        return product

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )