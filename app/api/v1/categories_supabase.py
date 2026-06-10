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
    ensure_safe_tenant_access(current_user, tenant_id)
    ensure_tenant_access_is_active(tenant_id)

    try:
        supabase = get_supabase_admin()

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
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ensure_safe_tenant_management(current_user, payload.tenant_id)
    ensure_tenant_access_is_active(payload.tenant_id)

    try:
        supabase = get_supabase_admin()

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

        category = response.data[0]

        write_audit_log(
            tenant_id=payload.tenant_id,
            action="category.create",
            entity_type="category",
            entity_id=category.get("id"),
            description=f"Categoria criada: {category.get('name')}",
            metadata={"category": category},
            current_user=current_user,
            request=request,
        )

        return category

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
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_admin()

        old_response = (
            supabase
            .table("categories")
            .select("*")
            .eq("id", category_id)
            .limit(1)
            .execute()
        )

        if not old_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada.",
            )

        old_category = old_response.data[0]
        tenant_id = old_category["tenant_id"]

        ensure_safe_tenant_management(current_user, tenant_id)
        ensure_tenant_access_is_active(tenant_id)

        update_data = payload.model_dump(exclude_unset=True)

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

        category = response.data[0]

        write_audit_log(
            tenant_id=tenant_id,
            action="category.update",
            entity_type="category",
            entity_id=category_id,
            description=f"Categoria atualizada: {category.get('name')}",
            metadata={
                "before": old_category,
                "changes": update_data,
                "after": category,
            },
            current_user=current_user,
            request=request,
        )

        return category

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )