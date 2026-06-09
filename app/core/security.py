from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security = HTTPBearer()


@lru_cache
def get_jwks_client() -> PyJWKClient:
    jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url)


def verify_supabase_token(token: str) -> dict[str, Any]:
    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            options={"verify_exp": True},
        )

        return payload

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    token = credentials.credentials
    payload = verify_supabase_token(token)

    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inválido.",
        )

    return {
        "id": user_id,
        "email": email,
        "access_token": token,
        "raw": payload,
    }