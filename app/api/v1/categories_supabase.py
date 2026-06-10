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


def dump_model(model: BaseModel, exclude_unset: bool = False) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)

    return model.dict(exclude_unset=exclude_unset)


def remove_column(payload: dict, column: str) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key != column
    }


def normalize_category_row(row: dict) -> dict:
    if "active" not in row and "is_active" in row:
        row["active"] = row.get("is_active")

    if "description" not in row:
        row["description"] = None

    return row


def build_category_insert_attempts(payload: dict) -> list[dict]:
    attempts: list[dict] = []

    base_payload = {
        "tenant_id": payload.get("tenant_id"),
        "name": payload.get("name"),
        "description": payload.get("description"),
        "active": payload.get("active", True),
    }

    attempts.append(base_payload)

    attempts.append({
        "tenant_id": payload.get("tenant_id"),
        "name": payload.get("name"),
        "description": payload.get("description"),
        "is_active": payload.get("active", True),
    })

    attempts.append({
        "tenant_id": payload.get("tenant_id"),
        "name": payload.get("name"),
        "active": payload.get("active", True),
    })

    attempts.append({
        "tenant_id": payload.get("tenant_id"),
        "name": payload.get("name"),
        "is_active": payload.get("active", True),
    })

    attempts.append({
        "tenant_id": payload.get("tenant_id"),
        "name": payload.get("name"),
    })

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


def build_category_update_attempts(payload: dict) -> list[dict]:
    attempts: list[dict] = []

    base_payload = {}

    if "name" in payload:
        base_payload["name"] = payload["name"]

    if "description" in payload:
        base_payload["description"] = payload["description"]

    if "active" in payload:
        base_payload["active"] = payload["active"]

    attempts.append(base_payload)

    if "active" in payload:
        is_active_payload = remove_column(base_payload, "active")
        is_active_payload["is_active"] = payload["active"]
        attempts.append(is_active_payload)

    attempts.append(remove_column(base_payload, "description"))

    if "active" in payload:
        minimal_is_active = remove_column(
            remove_column(base_payload, "description"),
            "active",
        )
        minimal_is_active["is_active"] = payload["active"]
        attempts.append(minimal_is_active)

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


def insert_category_with_fallback(payload: dict) -> dict:
    supabase = get_supabase_admin()

    attempts = build_category_insert_attempts(payload)
    last_error = None

    for attempt in attempts:
        try:
            response = (
                supabase
                .table("categories")
                .insert(attempt)
                .execute()
            )

            if response.data:
                return normalize_category_row(response.data[0])

        except Exception as error:
            last_error = error

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Não foi possível criar categoria: {str(last_error)}",
    )


def update_category_with_fallback(category_id: str, payload: dict) -> dict:
    supabase = get_supabase_admin()

    attempts = build_category_update_attempts(payload)
    last_error = None

    for attempt in attempts:
        try:
            response = (
                supabase
                .table("categories")
                .update(attempt)
                .eq("id", category_id)
                .execute()
            )

            if response.data:
                return normalize_category_row(response.data[0])

        except Exception as error:
            last_error = error

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Não foi possível atualizar categoria: {str(last_error)}",
    )


def safe_write_audit_log(**kwargs):
    try:
        write_audit_log(**kwargs)
    except Exception:
        return None


@router.get("")
def list_categories(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        ensure_safe_tenant_access(current_user, tenant_id)
        ensure_tenant_access_is_active(tenant_id)

        supabase = get_supabase_admin()

        response = (
            supabase
            .table("categories")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .execute()
        )

        categories = response.data or []

        return [normalize_category_row(category) for category in categories]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao listar categorias: {str(error)}",
        )


@router.post("")
def create_category(
    payload: CategoryCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        ensure_safe_tenant_management(current_user, payload.tenant_id)
        ensure_tenant_access_is_active(payload.tenant_id)

        category_payload = dump_model(payload)
        category = insert_category_with_fallback(category_payload)

        safe_write_audit_log(
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao criar categoria: {str(error)}",
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

        old_category = normalize_category_row(old_response.data[0])
        tenant_id = old_category["tenant_id"]

        ensure_safe_tenant_management(current_user, tenant_id)
        ensure_tenant_access_is_active(tenant_id)

        update_data = dump_model(payload, exclude_unset=True)
        category = update_category_with_fallback(category_id, update_data)

        safe_write_audit_log(
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao atualizar categoria: {str(error)}",
        )