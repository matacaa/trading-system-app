"""
services/api/middleware/rate_limiter.py
──────────────────────────────────────
Rate limiting por plan usando sliding window.

Usa Redis si disponible, diccionario en memoria como fallback.
Añade headers X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset.

Configuración por grupo de endpoint y plan:
    Auth (login/register)   : trial 5/min, starter 10/min, pro 20/min
    Read (GET)              : trial 30/min, starter 60/min, pro 120/min
    Write (POST/PUT/DELETE) : trial 10/min, starter 30/min, pro 60/min
    Backtest (POST /backtest): trial 2/min, starter 5/min, pro 10/min
    Training (POST /train)  : trial 1/min, starter 2/min, pro 5/min
    Squawks (GET /squawks)  : trial 10/min, starter 30/min, pro 60/min

Uso:
    En main.py:
        from services.api.middleware.rate_limiter import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

# ── Rate limits por grupo y plan ──────────────────────────────────────────────
# Formato: {grupo: {plan: max_requests_per_minute}}

_RATE_LIMITS: dict[str, dict[str, int]] = {
    "auth": {
        "trial": 5, "starter": 10, "pro": 20,
        "elite": 30, "enterprise": 60, "admin": 999,
    },
    "read": {
        "trial": 30, "starter": 60, "pro": 120,
        "elite": 200, "enterprise": 400, "admin": 999,
    },
    "write": {
        "trial": 10, "starter": 30, "pro": 60,
        "elite": 100, "enterprise": 200, "admin": 999,
    },
    "backtest": {
        "trial": 2, "starter": 5, "pro": 10,
        "elite": 20, "enterprise": 40, "admin": 999,
    },
    "training": {
        "trial": 1, "starter": 2, "pro": 5,
        "elite": 10, "enterprise": 20, "admin": 999,
    },
    "squawks": {
        "trial": 10, "starter": 30, "pro": 60,
        "elite": 100, "enterprise": 200, "admin": 999,
    },
}

# Window en segundos
_WINDOW = 60

# Rutas excluidas de rate limiting
_EXCLUDED = {"/api/health", "/api/stripe/webhook", "/docs", "/openapi.json"}


# ── Clasificación de endpoint ─────────────────────────────────────────────────


def _classify_endpoint(path: str, method: str) -> str:
    """Clasifica un request en un grupo de rate limiting."""
    p = path.rstrip("/")

    # Auth
    if p.startswith("/auth/"):
        return "auth"

    # Backtest (POST)
    if p == "/api/backtest" and method == "POST":
        return "backtest"

    # Training (POST)
    if p == "/api/train" and method == "POST":
        return "training"

    # Squawks (GET)
    if p.startswith("/api/squawks") and method == "GET":
        return "squawks"

    # Write (POST/PUT/DELETE genérico)
    if method in ("POST", "PUT", "DELETE", "PATCH"):
        return "write"

    # Read (GET genérico)
    return "read"


# ── Backend: in-memory sliding window ─────────────────────────────────────────
# Estructura: {key: [timestamp1, timestamp2, ...]}


class _InMemoryBackend:
    """Sliding window rate limiter con diccionario en memoria."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup: float = 0.0

    def check_and_increment(self, key: str, limit: int) -> tuple[bool, int, int]:
        """Verifica rate limit y añade el request actual.

        Args:
            key: identificador único (user_id:group o ip:group)
            limit: máximo de requests por ventana

        Returns:
            (allowed, remaining, reset_seconds)
        """
        now = time.time()
        cutoff = now - _WINDOW

        # Cleanup periódico (cada 60s) para evitar memory leak
        if now - self._last_cleanup > 60:
            self._cleanup(cutoff)
            self._last_cleanup = now

        # Filtrar requests dentro de la ventana
        window = self._windows[key]
        window[:] = [ts for ts in window if ts > cutoff]

        remaining = max(0, limit - len(window))

        if len(window) >= limit:
            # Reset = cuando expira el request más antiguo de la ventana
            reset_at = int(window[0] + _WINDOW - now) + 1
            return False, 0, reset_at

        # Permitido: registrar
        window.append(now)
        remaining = max(0, limit - len(window))
        return True, remaining, _WINDOW

    def _cleanup(self, cutoff: float) -> None:
        """Elimina ventanas vacías o expiradas."""
        empty_keys = [
            k for k, v in self._windows.items()
            if not v or v[-1] < cutoff
        ]
        for k in empty_keys:
            del self._windows[k]


class _RedisBackend:
    """Sliding window rate limiter con Redis sorted sets."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def check_and_increment(self, key: str, limit: int) -> tuple[bool, int, int]:
        """Verifica rate limit y añade el request actual usando Redis."""
        now = time.time()
        cutoff = now - _WINDOW
        rl_key = f"rl:{key}"

        pipe = self._redis.pipeline()
        # Eliminar entries expiradas
        pipe.zremrangebyscore(rl_key, 0, cutoff)
        # Contar entries en la ventana
        pipe.zcard(rl_key)
        # Obtener el entry más antiguo
        pipe.zrange(rl_key, 0, 0, withscores=True)
        results = pipe.execute()

        count = results[1]
        oldest = results[2]

        if count >= limit:
            reset_at = int(oldest[0][1] + _WINDOW - now) + 1 if oldest else _WINDOW
            return False, 0, reset_at

        # Permitido: añadir entry
        pipe2 = self._redis.pipeline()
        pipe2.zadd(rl_key, {f"{now}": now})
        pipe2.expire(rl_key, _WINDOW + 10)  # TTL = window + margen
        pipe2.execute()

        remaining = max(0, limit - count - 1)
        return True, remaining, _WINDOW


# ── Backend factory ───────────────────────────────────────────────────────────

_backend = None


def _get_backend():
    """Devuelve el backend de rate limiting (Redis si disponible, in-memory fallback)."""
    global _backend
    if _backend is not None:
        return _backend

    try:
        from shared.cache import _get_redis, _redis_available

        _get_redis()
        if _redis_available:
            import redis

            r = redis.from_url(
                __import__("os").getenv("REDIS_URL", ""),
                decode_responses=True,
            )
            r.ping()
            _backend = _RedisBackend(r)
            log.info("Rate limiter: usando Redis backend")
            return _backend
    except Exception:
        pass

    _backend = _InMemoryBackend()
    log.info("Rate limiter: usando in-memory backend (sin Redis)")
    return _backend


# ── Helpers para extraer identidad ────────────────────────────────────────────


def _extract_user_info(request: Request) -> tuple[str, str]:
    """Extrae user_id y plan del request.

    Si hay JWT en el header, decodifica (sin verificar — la auth dependency
    ya lo verifica después). Si no hay token, usa IP.

    Returns:
        (identifier, plan)
    """
    auth_header = request.headers.get("authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from services.api.auth.security import decode_token

            payload = decode_token(token)
            user_id = payload.get("sub", "")
            plan = payload.get("plan", "trial")
            if user_id:
                return user_id, plan
        except Exception:
            # Token inválido — el endpoint de auth lo rechazará después
            pass

    # Fallback: IP
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}", "trial"


# ── Middleware ────────────────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware que aplica rate limiting por plan."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # Excluir rutas que no necesitan rate limiting
        if path in _EXCLUDED or method == "OPTIONS":
            return await call_next(request)

        # Identificar usuario y plan
        identifier, plan = _extract_user_info(request)

        # Clasificar endpoint
        group = _classify_endpoint(path, method)

        # Obtener límite para este grupo + plan
        group_limits = _RATE_LIMITS.get(group, _RATE_LIMITS["read"])
        limit = group_limits.get(plan, group_limits.get("trial", 30))

        # Verificar rate limit
        backend = _get_backend()
        key = f"{identifier}:{group}"
        allowed, remaining, reset_seconds = backend.check_and_increment(key, limit)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": f"Límite de {limit} requests/min excedido para {group}",
                    "retry_after": reset_seconds,
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_seconds),
                    "Retry-After": str(reset_seconds),
                },
            )

        # Procesar request
        response = await call_next(request)

        # Añadir headers de rate limit
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_seconds)

        return response
