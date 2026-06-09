from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token
from app.schemas.tenant import TenantCreate, TenantResponse

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("tenants")
            .insert({
                "name": payload.name,
                "slug": payload.slug,
                "document": payload.document,
                "phone": payload.phone,
                "email": payload.email,
                "owner_user_id": current_user["id"],
            })
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível criar o tenant.",
            )

        tenant = response.data[0]

        return {
            "id": tenant["id"],
            "name": tenant["name"],
            "slug": tenant["slug"],
            "document": tenant.get("document"),
            "phone": tenant.get("phone"),
            "email": tenant.get("email"),
            "status": tenant["status"],
            "role": "owner",
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )


@router.get("/me", response_model=list[TenantResponse])
def list_my_tenants(
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("tenant_members")
            .select(
                "role, tenants(id, name, slug, document, phone, email, status)"
            )
            .eq("user_id", current_user["id"])
            .eq("active", True)
            .execute()
        )

        result = []

        for item in response.data:
            tenant = item.get("tenants")

            if tenant:
                result.append({
                    "id": tenant["id"],
                    "name": tenant["name"],
                    "slug": tenant["slug"],
                    "document": tenant.get("document"),
                    "phone": tenant.get("phone"),
                    "email": tenant.get("email"),
                    "status": tenant["status"],
                    "role": item["role"],
                })

        return result

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )