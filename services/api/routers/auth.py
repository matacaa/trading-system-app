"""
services/api/routers/auth.py
────────────────────────────
Endpoints de autenticación: registro, login, refresh token, perfil,
verificación de email, reenvío de verificación.

Endpoints:
    POST /auth/register        — Crear cuenta (envía email de verificación)
    POST /auth/login           — Login → access + refresh tokens
    POST /auth/refresh         — Renovar access token
    GET  /auth/me              — Perfil del usuario autenticado
    GET  /auth/verify-email    — Verificar email con token
    POST /auth/resend-verify   — Reenviar email de verificación
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr

from services.api.auth.dependencies import get_current_user
from services.api.auth.email import (
    create_verification_token,
    send_verification_email,
    verify_token,
)
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


class ResendVerifyRequest(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


# ── Password validation ──────────────────────────────────────────────────────

_RE_UPPER = re.compile(r"[A-Z]")
_RE_LOWER = re.compile(r"[a-z]")
_RE_SYMBOL = re.compile(r"[^A-Za-z0-9]")


def _validate_password(password: str) -> list[str]:
    """Valida requisitos de contraseña. Retorna lista de errores (vacía = OK)."""
    errors: list[str] = []
    if len(password) < 8:
        errors.append("Mínimo 8 caracteres")
    if not _RE_UPPER.search(password):
        errors.append("Al menos una mayúscula")
    if not _RE_LOWER.search(password):
        errors.append("Al menos una minúscula")
    if not _RE_SYMBOL.search(password):
        errors.append("Al menos un símbolo (!@#$%...)")
    return errors


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/auth/register", status_code=201)
async def register(req: RegisterRequest):
    """Crear cuenta nueva. Envía email de verificación."""

    # Validar password
    pwd_errors = _validate_password(req.password)
    if pwd_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": pwd_errors},
        )

    # Normalizar email
    email_lower = req.email.lower()

    # Verificar que el email no existe
    existing = query_one(
        "SELECT id FROM users WHERE LOWER(email) = %s", [email_lower]
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este email",
        )

    # Crear usuario (email_verified = false por defecto)
    hashed = hash_password(req.password)
    referral_code = secrets.token_urlsafe(8)[:12]

    user = query_one(
        """INSERT INTO users (email, password_hash, display_name, referral_code)
           VALUES (%s, %s, %s, %s)
           RETURNING id, email, plan""",
        [email_lower, hashed, req.display_name, referral_code],
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creando el usuario",
        )

    user_id = str(user["id"])

    # Crear user_preferences por defecto
    execute("INSERT INTO user_preferences (user_id) VALUES (%s)", [user_id])

    # Crear user_credits
    execute(
        "INSERT INTO user_credits (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
        [user_id],
    )

    log.info("Nuevo usuario registrado: %s (plan: %s)", user["email"], user["plan"])

    # Generar token de verificación y enviar email
    token = create_verification_token(user_id)
    email_sent = send_verification_email(email_lower, token)

    return {
        "message": "Cuenta creada. Revisa tu email para confirmar.",
        "email": email_lower,
        "email_sent": email_sent,
        "verification_token": token if not email_sent else None,
    }


@router.get("/auth/verify-email")
async def verify_email_endpoint(token: str = Query(...)):
    """Verificar email con token del enlace enviado por email."""

    result = verify_token(token)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado. Solicita uno nuevo.",
        )

    if result.get("already_verified"):
        return {
            "message": "Email ya verificado anteriormente.",
            "email": result["email"],
            "already_verified": True,
        }

    log.info("Email verificado: %s", result["email"])

    return {
        "message": "Email verificado correctamente. Ya puedes iniciar sesión.",
        "email": result["email"],
        "verified": True,
    }


@router.post("/auth/resend-verify")
async def resend_verification(req: ResendVerifyRequest):
    """Reenviar email de verificación."""

    email_lower = req.email.lower()
    user = query_one(
        "SELECT id, email_verified FROM users WHERE LOWER(email) = %s",
        [email_lower],
    )

    if not user:
        # No revelar si el email existe o no
        return {"message": "Si la cuenta existe, se ha enviado un email de verificación."}

    if user["email_verified"]:
        return {"message": "Email ya verificado. Puedes iniciar sesión."}

    token = create_verification_token(str(user["id"]))
    send_verification_email(email_lower, token)

    return {"message": "Si la cuenta existe, se ha enviado un email de verificación."}


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Login con email + password. Devuelve access + refresh tokens."""

    user = query_one(
        """SELECT id, email, password_hash, plan, is_active, email_verified
           FROM users WHERE LOWER(email) = LOWER(%s)""",
        [req.email],
    )

    if not user:
        log.warning("Login fallido — email no encontrado: %s", req.email)
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
        log.warning("Login fallido — password incorrecto para: %s", user["email"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )

    # Verificar email confirmado
    if not user["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "email_not_verified",
                "message": "Debes confirmar tu email antes de iniciar sesión. Revisa tu bandeja de entrada.",
                "email": user["email"],
            },
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
