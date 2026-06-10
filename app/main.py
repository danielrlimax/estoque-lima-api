from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.csrf import validate_csrf

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.APP_DEBUG,
)

allowed_origins = [
    settings.FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    path = request.url.path

    should_skip = (
        request.method.upper() in {"GET", "HEAD", "OPTIONS"}
        or path.endswith("/auth/login")
        or path.endswith("/auth/refresh")
        or path.endswith("/billing/asaas/webhook")
        or path == "/"
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi.json")
    )

    if not should_skip:
        validate_csrf(request)

    response = await call_next(request)
    return response


app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    if settings.APP_ENV == "production":
        return {
            "app": settings.APP_NAME,
            "status": "online",
        }

    return {
        "app": settings.APP_NAME,
        "status": "online",
        "docs": "/docs",
        "api": settings.API_PREFIX,
    }