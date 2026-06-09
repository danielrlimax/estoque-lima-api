from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.category import CategoryCreate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("categories")
            .insert({
                "tenant_id": payload.tenant_id,
                "name": payload.name,
                "description": payload.description,
                "active": payload.active,
            })
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar a categoria.",
            )

        return response.data[0]

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("categories")
            .select("id, tenant_id, name, description, active")
            .eq("tenant_id", tenant_id)
            .order("name")
            .execute()
        )

        return response.data

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))