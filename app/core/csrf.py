import secrets

from fastapi import HTTPException, Request, Response, status


CSRF_COOKIE_NAME = "limastock_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(
    response: Response,
    secure: bool,
    samesite: str,
):
    csrf_token = generate_csrf_token()

    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite=samesite,
        max_age=60 * 60 * 24,
        path="/",
    )

    return csrf_token


def clear_csrf_cookie(
    response: Response,
    secure: bool,
    samesite: str,
):
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=secure,
        samesite=samesite,
    )


def validate_csrf(request: Request):
    if request.method.upper() in SAFE_METHODS:
        return True

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(CSRF_HEADER_NAME)

    if not csrf_cookie or not csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF ausente.",
        )

    if not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF inválido.",
        )

    return True