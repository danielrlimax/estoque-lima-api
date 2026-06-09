from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    return {
        "status": "ok",
        "message": "Backend do Controle de Estoque está funcionando."
    }
