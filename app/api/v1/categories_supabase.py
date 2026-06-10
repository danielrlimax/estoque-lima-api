from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user
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


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    active: bool | None = None


def model_to_dict(model: BaseModel, exclude_unset: bool = False) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)

    return model.dict(exclude_unset=exclude_unset)


def normalize_category(category: dict) -> dict:
    if "active" not in category and "is_active" in category:
        category["active"] = category.get("is_active")

    if "active" not in category:
        category["active"] = True

    if "description" not in category:
        category["description"] = None

    return category


def create_category_attempts(payload: dict) -> list[dict]:
    tenant_id = payload["tenant_id"]
    name = payload["name"].strip()
    description = payload.get("description")

    attempts = [
        {
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "active": True,
        },
        {
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "is_active": True,
        },
        {
            "tenant_id": tenant_id,
            "name": name,
            "active": True,
        },
        {
            "tenant_id": tenant_id,
            "name": name,
            "is_active": True,
        },
        {
            "tenant_id": tenant_id,
            "name": name,
        },
    ]

    unique_attempts: list[dict] = []

    for attempt in attempts:
        clean_attempt = {
            key: value
            for key, value in attempt.items()
            if value is not None
        }

        if clean_attempt not in unique_attempts:
            unique_attempts.append(clean_attempt)

    return unique_attempts


def update_category_attempts(payload: dict) -> list[dict]:
    attempts: list[dict] = []

    base: dict = {}

    if "name" in payload and payload["name"] is not None:
        base["name"] = payload["name"].strip()

    if "description" in payload:
        base["description"] = payload["description"]

    if "active" in payload and payload["active"] is not None:
        base["active"] = payload["active"]

    attempts.append(base)

    if "active" in base:
        is_active_payload = {
            key: value
            for key, value in base.items()
            if key != "active"
        }
        is_active_payload["is_active"] = base["active"]
        attempts.append(is_active_payload)

    no_description = {
        key: value
        for key, value in base.items()
        if key != "description"
    }
    attempts.append(no_description)

    unique_attempts: list[dict] = []

    for attempt in attempts:
        clean_attempt = {
            key: value
            for key, value in attempt.items()
            if value is not None
        }

        if clean_attempt and clean_attempt not in unique_attempts:
            unique_attempts.append(clean_attempt)

    return unique_attempts


@router.get("")
def list_categories(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        ensure_safe_tenant_access(current_user, tenant_id)

        supabase = get_supabase_admin()

        response = (
            supabase
            .table("categories")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .execute()
        )

        return [
            normalize_category(category)
            for category in (response.data or [])
        ]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar categorias: {str(error)}",
        )


@router.post("")
def create_category(
    payload: CategoryCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        ensure_safe_tenant_management(current_user, payload.tenant_id)

        supabase = get_supabase_admin()
        data = model_to_dict(payload)

        last_error = None

        for attempt in create_category_attempts(data):
            try:
                response = (
                    supabase
                    .table("categories")
                    .insert(attempt)
                    .execute()
                )

                if response.data:
                    return normalize_category(response.data[0])

            except Exception as error:
                last_error = error

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não foi possível criar categoria: {str(last_error)}",
        )

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar categoria: {str(error)}",
        )


@router.patch("/{category_id}")
def update_category(
    category_id: str,
    payload: CategoryUpdateRequest,
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

        old_category = normalize_category(old_response.data[0])
        tenant_id = old_category["tenant_id"]

        ensure_safe_tenant_management(current_user, tenant_id)

        data = model_to_dict(payload, exclude_unset=True)
        last_error = None

        for attempt in update_category_attempts(data):
            try:
                response = (
                    supabase
                    .table("categories")
                    .update(attempt)
                    .eq("id", category_id)
                    .execute()
                )

                if response.data:
                    return normalize_category(response.data[0])

            except Exception as error:
                last_error = error

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não foi possível atualizar categoria: {str(last_error)}",
        )

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar categoria: {str(error)}",
        )