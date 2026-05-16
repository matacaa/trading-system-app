"""
services/api/routers/auth.py
────────────────────────────
Endpoints de autenticación: registro, login, refresh token, perfil.

Endpoints:
    POST /auth/register  — Crear cuenta nueva
    POST /auth/login     — Login con email + password → access + refresh tokens
    POST /auth/refresh   — Renovar access token usando refresh token
    GET  /auth/me        — Perfil del usuario autenticado
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from services.api.auth.dependencies import get_current_user
from services.api.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from shared.db import execute, query_one

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    """Crear cuenta nueva. Devuelve tokens para login inmediato."""

    # Validar password mínima
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La contraseña debe tener al menos 8 caracteres",
        )

    # Verificar que el email no existe
    existing = query_one("SELECT id FROM users WHERE email = %s", [req.email])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este email",
        )

    # Crear usuario
    hashed = hash_password(req.password)
    referral_code = secrets.token_urlsafe(8)[:12]  # código único de 12 chars

    user = query_one(
        """INSERT INTO users (email, password_hash, display_name, referral_code)
           VALUES (%s, %s, %s, %s)
           RETURNING id, email, plan""",
        [req.email, hashed, req.display_name, referral_code],
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creando el usuario",
        )

    # Crear user_preferences por defecto
    execute(
        "INSERT INTO user_preferences (user_id) VALUES (%s)",
        [str(user["id"])],
    )

    log.info("Nuevo usuario registrado: %s (plan: %s)", user["email"], user["plan"])

    # Generar tokens
    user_id = str(user["id"])
    access = create_access_token(user_id, user["email"], user["plan"])
    refresh = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=30 * 60,  # 30 minutos en segundos
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Login con email + password. Devuelve access + refresh tokens."""

    user = query_one(
        "SELECT id, email, password_hash, plan, is_active FROM users WHERE email = %s",
        [req.email],
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada. Contacta soporte.",
        )

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )

    # Actualizar last_login_at
    execute(
        "UPDATE users SET last_login_at = %s WHERE id = %s",
        [datetime.now(UTC).isoformat(), str(user["id"])],
    )

    user_id = str(user["id"])
    access = create_access_token(user_id, user["email"], user["plan"])
    refresh = create_refresh_token(user_id)

    log.info("Login: %s", user["email"])

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=30 * 60,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    """Renovar access token usando un refresh token válido."""

    try:
        payload = decode_token(req.refresh_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        ) from e

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de tipo incorrecto. Envía un refresh token.",
        )

    user_id = payload["sub"]

    # Verificar que el usuario sigue activo
    user = query_one(
        "SELECT id, email, plan, is_active FROM users WHERE id = %s",
        [user_id],
    )

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o desactivado",
        )

    access = create_access_token(str(user["id"]), user["email"], user["plan"])
    new_refresh = create_refresh_token(str(user["id"]))

    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=30 * 60,
    )


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """Perfil del usuario autenticado."""

    row = query_one(
        """SELECT id, email, display_name, plan, trial_end, is_active,
                  email_verified, country, locale, timezone,
                  referral_code, created_at, last_login_at
           FROM users WHERE id = %s""",
        [user["id"]],
    )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    # Añadir preferencias
    prefs = query_one(
        """SELECT tickers, notification_prefs, theme, language,
                  onboarding_completed, risk_profile, default_capital,
                  default_timeframe, max_tickers
           FROM user_preferences WHERE user_id = %s""",
        [user["id"]],
    )

    return {
        "user": row,
        "preferences": prefs,
    }
