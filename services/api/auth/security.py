"""
services/api/auth/security.py
─────────────────────────────
Password hashing (bcrypt) y JWT tokens (HS256).

Uso:
    from services.api.auth.security import hash_password, verify_password
    from services.api.auth.security import create_access_token, create_refresh_token
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

# ── Config ────────────────────────────────────────────────────────────────────

# JWT_SECRET_KEY: DEBE estar en .env. Si no existe, falla ruidosamente.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no configurado. Genera uno con: "
        "python -c \"import secrets; print(secrets.token_urlsafe(64))\" "
        "y añádelo a .env"
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# ── Password hashing ─────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hashea una contraseña con bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash bcrypt."""
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWT tokens ────────────────────────────────────────────────────────────────


def create_access_token(user_id: str, email: str, plan: str) -> str:
    """Crea un JWT access token (corta duración, para cada request)."""
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "plan": plan,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Crea un JWT refresh token (larga duración, solo para renovar access)."""
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica y valida un JWT. Lanza JWTError si es inválido o expirado."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
