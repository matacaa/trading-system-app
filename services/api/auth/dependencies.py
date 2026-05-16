"""
services/api/auth/dependencies.py
─────────────────────────────────
FastAPI dependencies para inyectar el usuario autenticado en los endpoints.

Uso en routers:
    from services.api.auth.dependencies import get_current_user

    @router.get("/algo")
    async def algo(user: dict = Depends(get_current_user)):
        user_id = user["id"]
        plan = user["plan"]
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.api.auth.security import decode_token

log = logging.getLogger(__name__)

# HTTPBearer extrae el token del header "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(auto_error=True)
_bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    Dependency que valida el JWT y devuelve el usuario.

    Returns:
        dict con keys: id, email, plan, type

    Raises:
        HTTPException 401 si el token es inválido, expirado, o no es access token
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception as e:
        log.warning("Token inválido: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Solo aceptamos access tokens, no refresh tokens
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de tipo incorrecto. Usa un access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": payload["sub"],
        "email": payload.get("email", ""),
        "plan": payload.get("plan", "trial"),
    }


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme_optional),
) -> dict | None:
    """
    Dependency opcional: devuelve el usuario si hay token válido, None si no.
    Útil para endpoints que funcionan con o sin auth (ej: datos públicos
    que muestran info extra si estás logueado).
    """
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        return {
            "id": payload["sub"],
            "email": payload.get("email", ""),
            "plan": payload.get("plan", "trial"),
        }
    except Exception:
        return None
