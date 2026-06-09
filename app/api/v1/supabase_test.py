from fastapi import APIRouter, HTTPException

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/supabase-test", tags=["Supabase Test"])


@router.get("")
def test_supabase_connection():
    try:
        supabase = get_supabase()

        response = (
            supabase
            .table("plans")
            .select("id, code, name, active")
            .limit(5)
            .execute()
        )

        return {
            "supabase": "connected",
            "data": response.data,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )