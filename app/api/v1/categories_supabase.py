from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.subscription_guard import ensure_tenant_access_is_active
from app.db.supabase_client import get_supabase_admin, get_supabase_with_token

router = APIRouter(prefix="/categories", tags=["Categories"])


class CategoryCreateRequest(BaseModel):
    tenant_id: str
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    active: bool = True


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    active: bool | None = None


@router.get("")
def list_categories(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("categories")
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


@router.post("")
def create_category(
    payload: CategoryCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    ensure_tenant_access_is_active(payload.tenant_id)

    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("categories")
            .insert(payload.model_dump())
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar categoria.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.patch("/{category_id}")
def update_category(
    category_id: str,
    payload: CategoryUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase_admin = get_supabase_admin()

        category_response = (
            supabase_admin
            .table("categories")
            .select("id, tenant_id")
            .eq("id", category_id)
            .limit(1)
            .execute()
        )

        if not category_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada.",
            )

        tenant_id = category_response.data[0]["tenant_id"]

        ensure_tenant_access_is_active(tenant_id)

        update_data = payload.model_dump(exclude_unset=True)

        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("categories")
            .update(update_data)
            .eq("id", category_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível atualizar categoria.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )