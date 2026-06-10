from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.security import get_current_user
from app.db.supabase_client import get_supabase
from app.schemas.auth import LoginRequest

router = APIRouter(prefix="/auth", tags=["Auth"])


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str | None,
):
    response.set_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=60 * 60,
        path="/",
    )

    if refresh_token:
        response.set_cookie(
            key=settings.COOKIE_REFRESH_NAME,
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=60 * 60 * 24 * 30,
            path="/",
        )


def clear_auth_cookies(response: Response):
    response.delete_cookie(
        key=settings.COOKIE_ACCESS_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    response.delete_cookie(
        key=settings.COOKIE_REFRESH_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    try:
        supabase = get_supabase()

        auth_response = supabase.auth.sign_in_with_password(
            {
                "email": payload.email,
                "password": payload.password,
            }
        )

        if not auth_response.session or not auth_response.session.access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-mail ou senha inválidos.",
            )

        set_auth_cookies(
            response=response,
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
        )

        return {
            "authenticated": True,
            "user": {
                "id": auth_response.user.id,
                "email": auth_response.user.email,
            },
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )


@router.post("/refresh")
def refresh_session(request: Request, response: Response):
    try:
        refresh_token = request.cookies.get(settings.COOKIE_REFRESH_NAME)

        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token não encontrado.",
            )

        supabase = get_supabase()

        auth_response = supabase.auth.refresh_session(refresh_token)

        if not auth_response.session or not auth_response.session.access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Não foi possível renovar a sessão.",
            )

        set_auth_cookies(
            response=response,
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
        )

        return {
            "refreshed": True,
            "user": {
                "id": auth_response.user.id if auth_response.user else None,
                "email": auth_response.user.email if auth_response.user else None,
            },
        }

    except HTTPException:
        raise
    except Exception:
        clear_auth_cookies(response)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Faça login novamente.",
        )


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookies(response)

    return {
        "logged_out": True,
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user.get("id"),
        "email": current_user.get("email"),
    }