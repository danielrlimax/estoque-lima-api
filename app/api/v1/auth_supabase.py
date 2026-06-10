from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.audit import write_audit_log
from app.core.config import settings
from app.core.csrf import clear_csrf_cookie, set_csrf_cookie
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
def login(payload: LoginRequest, request: Request, response: Response):
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

        csrf_token = set_csrf_cookie(
            response=response,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )

        write_audit_log(
            action="auth.login",
            entity_type="auth",
            entity_id=auth_response.user.id,
            description="Usuário fez login no sistema.",
            metadata={
                "email": auth_response.user.email,
            },
            current_user={
                "id": auth_response.user.id,
                "email": auth_response.user.email,
            },
            request=request,
        )

        return {
            "authenticated": True,
            "csrf_token": csrf_token,
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

        csrf_token = set_csrf_cookie(
            response=response,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )

        return {
            "refreshed": True,
            "csrf_token": csrf_token,
            "user": {
                "id": auth_response.user.id if auth_response.user else None,
                "email": auth_response.user.email if auth_response.user else None,
            },
        }

    except HTTPException:
        raise
    except Exception:
        clear_auth_cookies(response)
        clear_csrf_cookie(
            response=response,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Faça login novamente.",
        )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    write_audit_log(
        action="auth.logout",
        entity_type="auth",
        entity_id=current_user.get("id"),
        description="Usuário saiu do sistema.",
        current_user=current_user,
        request=request,
    )

    clear_auth_cookies(response)
    clear_csrf_cookie(
        response=response,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return {
        "logged_out": True,
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user.get("id"),
        "email": current_user.get("email"),
    }