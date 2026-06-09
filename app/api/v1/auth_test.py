from fastapi import APIRouter, Depends

from app.core.security import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "message": "Usuário autenticado com sucesso.",
        "user": {
            "id": current_user["id"],
            "email": current_user.get("email"),
        }
    }