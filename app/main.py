from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_cors_origins, settings
from app.core.csrf import validate_csrf
from app.core.rate_limit import enforce_rate_limit
from app.core.security_headers import apply_security_headers

app = FastAPI(title=settings.APP_NAME, debug=settings.APP_DEBUG)

allowed_origins = get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=(
        r"^https://.*\.vercel\.app$|"
        r"^http://localhost:3000$|"
        r"^http://127\.0\.0\.1:3000$"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-CSRF-Token",
        "x-csrf-token",
    ],
    expose_headers=["Set-Cookie"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method.upper()

    if method == "OPTIONS":
        response = await call_next(request)
        apply_security_headers(response)
        return response

    if path.endswith("/auth/login"):
        enforce_rate_limit(
            request=request,
            limit=8,
            window_seconds=60,
            scope="auth_login",
        )
    elif path.endswith("/auth/refresh"):
        enforce_rate_limit(
            request=request,
            limit=30,
            window_seconds=60,
            scope="auth_refresh",
        )
    elif path.endswith("/billing/asaas/webhook"):
        enforce_rate_limit(
            request=request,
            limit=120,
            window_seconds=60,
            scope="asaas_webhook",
        )
    elif path.startswith(settings.API_PREFIX):
        enforce_rate_limit(
            request=request,
            limit=180,
            window_seconds=60,
            scope="api_general",
        )

    should_skip_csrf = (
        method in {"GET", "HEAD", "OPTIONS"}
        or path.endswith("/auth/login")
        or path.endswith("/auth/refresh")
        or path.endswith("/billing/asaas/webhook")
        or path == "/"
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi.json")
    )

    if not should_skip_csrf:
        validate_csrf(request)

    response = await call_next(request)
    apply_security_headers(response)
    return response


app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "status": "online",
        "environment": settings.APP_ENV,
        "cors_origins": allowed_origins,
    }