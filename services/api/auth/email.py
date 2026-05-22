"""
services/api/auth/email.py
──────────────────────────
Servicio de verificación de email: genera token, envía email, verifica.

Variables de entorno necesarias:
    SMTP_HOST       — ej: smtp.gmail.com, smtp.office365.com
    SMTP_PORT       — ej: 587
    SMTP_USER       — ej: noreply@squawksml.com
    SMTP_PASSWORD   — contraseña o app password
    SMTP_FROM       — ej: Squawks ML <noreply@squawksml.com>
    APP_BASE_URL    — ej: http://localhost:3000 o https://app.squawksml.com
"""

from __future__ import annotations

import logging
import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shared.db import execute, query_one

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Squawks ML <noreply@squawksml.com>")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:3000")

TOKEN_EXPIRY_HOURS = 24


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


# ── Token management ─────────────────────────────────────────────────────────


def create_verification_token(user_id: str) -> str:
    """Genera un token de verificación y lo guarda en la DB."""
    token = secrets.token_urlsafe(48)
    expires = datetime.now(UTC) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    # Invalidar tokens previos del usuario
    execute(
        "DELETE FROM email_verification_tokens WHERE user_id = %s AND used_at IS NULL",
        [user_id],
    )

    execute(
        """INSERT INTO email_verification_tokens (user_id, token, expires_at)
           VALUES (%s, %s, %s)""",
        [user_id, token, expires.isoformat()],
    )

    return token


def verify_token(token: str) -> dict | None:
    """Valida un token. Retorna user info si es válido, None si no.

    Marca el token como usado y pone email_verified = true en users.
    """
    row = query_one(
        """SELECT t.id AS token_id, t.user_id, t.expires_at, t.used_at,
                  u.email, u.email_verified
           FROM email_verification_tokens t
           JOIN users u ON u.id = t.user_id
           WHERE t.token = %s""",
        [token],
    )

    if not row:
        return None

    # Ya usado
    if row["used_at"]:
        return {"already_verified": True, "email": row["email"]}

    # Expirado
    if datetime.now(UTC) > row["expires_at"].replace(tzinfo=UTC):
        return None

    # Marcar como usado
    execute(
        "UPDATE email_verification_tokens SET used_at = %s WHERE id = %s",
        [datetime.now(UTC).isoformat(), str(row["token_id"])],
    )

    # Activar email_verified en user
    execute(
        "UPDATE users SET email_verified = true WHERE id = %s",
        [str(row["user_id"])],
    )

    return {"verified": True, "email": row["email"], "user_id": str(row["user_id"])}


# ── Email sending ────────────────────────────────────────────────────────────


def send_verification_email(email: str, token: str) -> bool:
    """Envía el email de verificación. Retorna True si se envió."""
    verify_url = f"{APP_BASE_URL}/verify-email?token={token}"

    if not _smtp_configured():
        log.warning(
            "SMTP no configurado. Token de verificación para %s: %s",
            email,
            token,
        )
        log.warning("URL de verificación: %s", verify_url)
        return False

    subject = "Confirma tu cuenta — Squawks ML"

    html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,system-ui,sans-serif">
<div style="max-width:480px;margin:40px auto;padding:32px;background:#1e293b;border-radius:16px;border:1px solid rgba(255,255,255,0.06)">
  <div style="text-align:center;margin-bottom:24px">
    <span style="display:inline-block;padding:8px 16px;border-radius:10px;background:linear-gradient(135deg,#06b6d4,#8b5cf6);color:white;font-weight:700;font-size:18px">
      Squawks ML
    </span>
  </div>
  <h2 style="color:#f1f5f9;font-size:20px;text-align:center;margin:0 0 8px">
    Confirma tu email
  </h2>
  <p style="color:#94a3b8;font-size:14px;text-align:center;line-height:1.6;margin:0 0 24px">
    Haz click en el botón para activar tu cuenta.
    El enlace expira en {TOKEN_EXPIRY_HOURS} horas.
  </p>
  <div style="text-align:center;margin-bottom:24px">
    <a href="{verify_url}"
       style="display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#06b6d4,#0891b2);color:white;text-decoration:none;border-radius:10px;font-weight:600;font-size:14px">
      Verificar email
    </a>
  </div>
  <p style="color:#64748b;font-size:11px;text-align:center;margin:0">
    Si no creaste esta cuenta, ignora este email.
  </p>
</div>
</body>
</html>"""

    text = f"Confirma tu cuenta en Squawks ML: {verify_url}"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = email
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, email, msg.as_string())

        log.info("Email de verificación enviado a %s", email)
        return True

    except Exception:
        log.exception("Error enviando email de verificación a %s", email)
        return False
