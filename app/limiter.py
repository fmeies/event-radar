from fastapi import Request
from slowapi import Limiter

_TRUSTED_PROXIES = {"127.0.0.1", "::1"}


def _get_client_ip(request: Request) -> str:
    """Return the real client IP.

    When the request arrives from a trusted local proxy (Apache), read the
    client IP from X-Forwarded-For / X-Real-IP so rate limits apply per
    real client rather than per proxy address. Direct connections use the
    socket address as-is to prevent header spoofing by external clients.
    """
    peer = request.client.host if request.client else ""
    if peer in _TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For", "")
        real_ip = request.headers.get("X-Real-IP") or (
            forwarded.split(",")[0].strip() if forwarded else ""
        )
        if real_ip:
            return real_ip
    return peer or "unknown"


limiter = Limiter(key_func=_get_client_ip)
