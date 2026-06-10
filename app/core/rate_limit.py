import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """
    Rate limiter simples para V1.

    Importante:
    - Funciona bem para um único processo/instância.
    - Em produção grande, o ideal é trocar por Redis.
    """

    def __init__(self):
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        bucket = self.requests[key]

        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()

        if len(bucket) >= limit:
            return False

        bucket.append(now)
        return True


rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")

    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return "unknown"


def enforce_rate_limit(
    request: Request,
    limit: int,
    window_seconds: int,
    scope: str,
):
    client_ip = get_client_ip(request)
    key = f"{scope}:{client_ip}"

    allowed = rate_limiter.is_allowed(
        key=key,
        limit=limit,
        window_seconds=window_seconds,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas requisições. Aguarde um pouco e tente novamente.",
        )