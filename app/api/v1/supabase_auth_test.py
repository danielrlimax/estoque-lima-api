from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.supabase_client import get_supabase_with_token

router = APIRouter(prefix="/supabase-auth-test", tags=["Supabase Auth Test"])


@router.get("")
def test_authenticated_supabase_connection(
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase = get_supabase_with_token(current_user["access_token"])

        response = (
            supabase
            .table("tenants")
            .select("id, name, slug, status")
            .limit(10)
            .execute()
        )

        return {
            "user": {
                "id": current_user["id"],
                "email": current_user["email"],
            },
            "supabase": "authenticated",
            "data": response.data,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )