"""
time.py
───────
Utilidades de timezone para evitar bugs UTC/ET.

Resuelve F-28, F-41 del informe de Fase 2 (reset de contadores diarios en zona horaria incorrecta).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytz

# Zona horaria del mercado US (NYSE/NASDAQ)
ET = pytz.timezone("America/New_York")


def now_et() -> datetime:
    """Hora actual en Eastern Time (mercado US)."""
    return datetime.now(ET)


def now_utc() -> datetime:
    """Hora actual en UTC."""
    return datetime.now(UTC)


def today_et() -> date:
    """Fecha actual en Eastern Time (para contadores de día de trading)."""
    return now_et().date()


def start_of_day_et_as_utc(d: date | None = None) -> datetime:
    """Medianoche ET del día dado, expresada en UTC.
    
    Útil para queries tipo "trades de hoy" donde hoy significa en ET.
    """
    if d is None:
        d = today_et()
    et_midnight = ET.localize(datetime.combine(d, datetime.min.time()))
    return et_midnight.astimezone(UTC)


def utc_isoformat(dt: datetime | None = None) -> str:
    """ISO string en UTC."""
    if dt is None:
        dt = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()
