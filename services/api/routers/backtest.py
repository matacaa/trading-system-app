"""
services/api/routers/backtest.py
────────────────────────────────
Endpoints de backtest — Fase 6.4 reescritura completa.

POST   /backtest           — lanzar con validaciones de plan
GET    /backtest/list       — lista con filtros
GET    /backtest/usage      — uso este mes
GET    /backtest/{id}       — detalle
GET    /backtest/{id}/equity — serie temporal equity curve
DELETE /backtest/{id}       — eliminar
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.api.auth.dependencies import get_active_user, get_current_user
from shared.db import get_conn, query
from shared.plan_limits import get_plan_limits, is_guardrail_available

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class BacktestRequest(BaseModel):
    name: str = ""
    ticker: str = "AAPL"
    direction: str = "long"
    date_from: str  # YYYY-MM-DD
    date_to: str
    models_config: dict[str, float] = Field(default_factory=dict)
    models_enabled: bool = True
    guardrails_config: dict[str, Any] = Field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_backtests_this_month(user_id: str) -> int:
    rows = query(
        """SELECT COUNT(*) as cnt FROM backtest_runs
           WHERE user_id = %s
           AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)""",
        [user_id],
    )
    return rows[0]["cnt"] if rows else 0


def _count_backtests_saved(user_id: str) -> int:
    rows = query(
        "SELECT COUNT(*) as cnt FROM backtest_runs WHERE user_id = %s",
        [user_id],
    )
    return rows[0]["cnt"] if rows else 0


def _get_extra_backtests(user_id: str) -> int:
    rows = query(
        "SELECT extra_backtests FROM user_credits WHERE user_id = %s",
        [user_id],
    )
    return rows[0]["extra_backtests"] if rows else 0


def _validate_backtest(req: BacktestRequest, user: dict) -> list[str]:
    """Valida el request contra los límites del plan."""
    errors = []
    plan = user.get("plan", "trial")
    limits = get_plan_limits(plan)
    user_id = user["id"]

    # 1. Ticker existe
    t_rows = query(
        "SELECT ticker FROM ticker_universe WHERE ticker = %s AND is_active = true",
        [req.ticker],
    )
    if not t_rows:
        errors.append(f"Ticker '{req.ticker}' no existe o no está activo")

    # 2. Hist days
    try:
        d_from = date.fromisoformat(req.date_from)
        d_to = date.fromisoformat(req.date_to)
        days = (d_to - d_from).days
        if days <= 0:
            errors.append("date_to debe ser posterior a date_from")
        elif days > limits["max_hist_days"]:
            errors.append(
                f"Ventana de {days} días excede el límite del plan "
                f"({limits['max_hist_days']} días)"
            )
    except ValueError:
        errors.append("Formato de fecha inválido (usar YYYY-MM-DD)")

    # 3. Models count
    if req.models_enabled and len(req.models_config) > limits["max_models"]:
        errors.append(f"Máximo {limits['max_models']} modelos en plan {plan}")

    # 4. Weights sum to 100
    if req.models_enabled and req.models_config:
        total_weight = sum(req.models_config.values())
        if abs(total_weight - 100) > 0.01:
            errors.append(f"Los pesos deben sumar 100 (suman {total_weight})")

    # 5. Backtests/month
    used = _count_backtests_this_month(user_id)
    extra = _get_extra_backtests(user_id)
    limit_month = limits["max_backtests_month"] + extra
    if used >= limit_month:
        errors.append(f"Límite de backtests/mes alcanzado ({used}/{limit_month})")

    # 6. Guardrails in plan
    for g_name in req.guardrails_config:
        if not is_guardrail_available(plan, g_name):
            errors.append(f"Guardrail '{g_name}' no disponible en plan {plan}")

    # 7. Direction
    if req.direction not in ("long", "short"):
        errors.append("direction debe ser 'long' o 'short'")

    return errors


def _run_backtest_sync(req: BacktestRequest) -> dict:
    """Ejecuta el backtest via subprocess (motor legacy)."""
    from shared.legacy_runners import generate_backtest_yaml, run_pipeline

    modelos_legacy = []
    if req.models_enabled and req.models_config:
        for exp_name, weight in req.models_config.items():
            modelos_legacy.append({
                "experiment_name": exp_name,
                "activo": True,
                "peso": weight / 100.0,
            })
    else:
        modelos_legacy = [{"experiment_name": "default", "activo": False, "peso": 0}]

    bt_name = (
        req.name.strip()
        or f"bt_{req.ticker.lower()}_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}"
    )
    tmp, bt_name = generate_backtest_yaml(
        name=bt_name,
        tickers=[req.ticker],
        test_start=req.date_from,
        test_end=req.date_to,
        modelos=modelos_legacy,
        guardrails=req.guardrails_config,
    )
    try:
        result = run_pipeline(
            [sys.executable, "-m", "apps.ml_sandbox.backtest", "--config", str(tmp)],
            timeout=600,
        )
        return {"success": result.get("success", False), "backtest_name": bt_name, **result}
    finally:
        tmp.unlink(missing_ok=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/backtest")
async def run_backtest(req: BacktestRequest, user: dict = Depends(get_active_user)):
    """Lanza un nuevo backtest con validaciones de plan."""
    errors = _validate_backtest(req, user)
    if errors:
        raise HTTPException(422, detail={"errors": errors})

    user_id = user["id"]
    start_time = time.time()
    result = _run_backtest_sync(req)
    duration = round(time.time() - start_time, 2)

    bt_name = result.get("backtest_name", req.name)

    # Guardar en DB con campos nuevos
    conn = get_conn()
    bt_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO backtest_runs
                   (name, user_id, ticker, direction, date_from, date_to,
                    guardrails_config, models_config, models_enabled,
                    config, status, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                [
                    bt_name, user_id, req.ticker, req.direction,
                    req.date_from, req.date_to,
                    json.dumps(req.guardrails_config),
                    json.dumps(req.models_config),
                    req.models_enabled,
                    json.dumps({"duration": duration}),
                    "completed" if result.get("success") else "failed",
                    datetime.now(UTC),
                ],
            )
            row = cur.fetchone()
            bt_id = row[0] if row else None
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error(f"Error guardando backtest: {e}")
    finally:
        conn.close()

    # Leer métricas si tuvo éxito
    metrics = None
    if result.get("success"):
        m_rows = query(
            "SELECT * FROM backtest_metrics WHERE backtest_name = %s LIMIT 1",
            [bt_name],
        )
        metrics = m_rows[0] if m_rows else None

    return {
        "id": str(bt_id) if bt_id else None,
        "backtest_name": bt_name,
        "success": result.get("success", False),
        "duration": duration,
        "metrics": metrics,
    }


@router.get("/backtest/list")
async def list_backtests(
    user: dict = Depends(get_current_user),
    ticker: str | None = Query(None),
    limit: int = Query(50, le=100),
):
    """Lista backtests del usuario con filtro opcional por ticker."""
    params: list = [user["id"]]
    sql = """SELECT id, name, ticker, direction, date_from, date_to,
                    guardrails_config, models_config, models_enabled,
                    status, created_at, total_trades, pnl_total, pnl_pct,
                    win_rate, sharpe_ratio, equity_curve
             FROM backtest_runs
             WHERE (user_id = %s OR user_id IS NULL)"""
    if ticker:
        sql += " AND ticker = %s"
        params.append(ticker)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    rows = query(sql, params)
    return {"backtests": rows or []}


@router.get("/backtest/usage")
async def backtest_usage(user: dict = Depends(get_current_user)):
    """Uso de backtests este mes vs límite del plan."""
    user_id = user["id"]
    plan = user.get("plan", "trial")
    limits = get_plan_limits(plan)
    used = _count_backtests_this_month(user_id)
    extra = _get_extra_backtests(user_id)
    limit_total = limits["max_backtests_month"] + extra
    saved = _count_backtests_saved(user_id)
    return {
        "used_this_month": used,
        "limit_month": limit_total,
        "remaining_month": max(0, limit_total - used),
        "saved_total": saved,
        "limit_saved": limits["max_backtests_saved"],
    }


@router.get("/backtest/{bt_id}")
async def get_backtest(bt_id: str, user: dict = Depends(get_current_user)):
    """Detalle de un backtest con config + métricas."""
    rows = query(
        """SELECT br.*, bm.total_trades, bm.pnl_total, bm.pnl_pct,
                  bm.win_rate, bm.sharpe_ratio, bm.max_drawdown
           FROM backtest_runs br
           LEFT JOIN backtest_metrics bm ON bm.backtest_name = br.name
           WHERE br.id = %s AND (br.user_id = %s OR br.user_id IS NULL)""",
        [bt_id, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Backtest no encontrado")
    return {"backtest": rows[0]}


@router.get("/backtest/{bt_id}/equity")
async def get_equity_curve(bt_id: str, user: dict = Depends(get_current_user)):
    """Serie temporal equity curve para chart."""
    rows = query(
        """SELECT equity_curve FROM backtest_runs
           WHERE id = %s AND (user_id = %s OR user_id IS NULL)""",
        [bt_id, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Backtest no encontrado")
    return {"equity_curve": rows[0].get("equity_curve") or []}


@router.delete("/backtest/{bt_id}")
async def delete_backtest(bt_id: str, user: dict = Depends(get_current_user)):
    """Elimina un backtest guardado."""
    rows = query(
        "SELECT id, name FROM backtest_runs WHERE id = %s AND user_id = %s",
        [bt_id, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Backtest no encontrado o no tienes permiso")
    bt_name = rows[0]["name"]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM backtest_trades WHERE backtest_name = %s", [bt_name])
            cur.execute("DELETE FROM backtest_metrics WHERE backtest_name = %s", [bt_name])
            cur.execute(
                "DELETE FROM backtest_runs WHERE id = %s AND user_id = %s",
                [bt_id, user["id"]],
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error eliminando backtest: {e}") from e
    finally:
        conn.close()
    return {"deleted": True, "id": bt_id}
