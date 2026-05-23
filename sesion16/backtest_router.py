"""
services/api/routers/backtest.py — Sesión 16
────────────────────────────────────────────
Endpoints de backtest — dual-dirección (LONG + SHORT simultáneo).

POST   /backtest            — lanzar con validaciones de plan
GET    /backtest/list        — lista con filtros
GET    /backtest/usage       — uso este mes
GET    /backtest/{id}        — detalle
GET    /backtest/{id}/equity — serie temporal equity curve
DELETE /backtest/{id}        — eliminar

Cambios sesión 16:
    - Eliminado campo direction (ahora siempre evalúa LONG + SHORT)
    - Equity curve se guarda en backtest_runs.equity_curve como JSONB
    - Métricas separadas por dirección (long_*, short_*)
    - Motor no crashea si no hay modelos (score=50 neutral)
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
    # direction eliminado — ahora siempre evalúa LONG + SHORT
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

    return errors


def _run_backtest_sync(req: BacktestRequest) -> dict:
    """Ejecuta el backtest via subprocess (motor dual-dirección)."""
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
    """Lanza un nuevo backtest dual-dirección con validaciones de plan."""
    errors = _validate_backtest(req, user)
    if errors:
        raise HTTPException(422, detail={"errors": errors})

    user_id = user["id"]
    start_time = time.time()
    result = _run_backtest_sync(req)
    duration = round(time.time() - start_time, 2)

    bt_name = result.get("backtest_name", req.name)

    # Guardar en DB
    bt_id = None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO backtest_runs
                       (name, user_id, ticker, direction, date_from, date_to,
                        guardrails_config, models_config, models_enabled,
                        config, status, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (name) DO UPDATE SET
                        user_id = EXCLUDED.user_id, ticker = EXCLUDED.ticker,
                        direction = EXCLUDED.direction, date_from = EXCLUDED.date_from,
                        date_to = EXCLUDED.date_to, guardrails_config = EXCLUDED.guardrails_config,
                        models_config = EXCLUDED.models_config, models_enabled = EXCLUDED.models_enabled,
                        config = EXCLUDED.config, status = EXCLUDED.status, created_at = EXCLUDED.created_at
                       RETURNING id""",
                    [
                        bt_name, user_id, req.ticker,
                        "both",  # direction = "both" (dual-dirección)
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
    except Exception as e:
        log.error(f"Error guardando backtest: {e}")

    # Copiar métricas + equity curve desde backtest_metrics
    metrics = None
    if result.get("success") and bt_id:
        m_rows = query(
            """SELECT total_trades, pnl_total, pnl_pct_total AS pnl_pct,
                      win_rate, sharpe_ratio, max_drawdown
               FROM backtest_metrics WHERE backtest_name = %s LIMIT 1""",
            [bt_name],
        )
        if m_rows:
            metrics = m_rows[0]
            try:
                # Construir equity curve desde trades
                t_rows = query(
                    """SELECT ts_salida, pnl, side FROM backtest_trades
                       WHERE backtest_name = %s AND ejecutada = true
                       AND motivo_salida != 'abierta'
                       ORDER BY ts_salida""",
                    [bt_name],
                )
                equity_curve = []
                running = 100000  # capital inicial por defecto
                if t_rows:
                    for tr in t_rows:
                        running += tr.get("pnl", 0)
                        equity_curve.append({
                            "date": str(tr["ts_salida"]),
                            "value": round(running, 2),
                            "trade_direction": tr.get("side", "long"),
                        })

                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """UPDATE backtest_runs
                               SET total_trades = %s, pnl_total = %s, pnl_pct = %s,
                                   win_rate = %s, sharpe_ratio = %s, max_drawdown = %s,
                                   equity_curve = %s
                               WHERE id = %s""",
                            [
                                metrics.get("total_trades"),
                                metrics.get("pnl_total"),
                                metrics.get("pnl_pct"),
                                metrics.get("win_rate"),
                                metrics.get("sharpe_ratio"),
                                metrics.get("max_drawdown"),
                                json.dumps(equity_curve) if equity_curve else None,
                                bt_id,
                            ],
                        )
            except Exception as e:
                log.warning(f"Error actualizando métricas/equity en backtest_runs: {e}")

        # Leer métricas direccionales de backtest_trades
        try:
            dir_rows = query(
                """SELECT side,
                          COUNT(*) as cnt,
                          SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                          COALESCE(SUM(pnl), 0) as pnl_sum
                   FROM backtest_trades
                   WHERE backtest_name = %s AND ejecutada = true
                   AND motivo_salida != 'abierta'
                   GROUP BY side""",
                [bt_name],
            )
            dir_metrics = {}
            for dr in (dir_rows or []):
                side = dr["side"] or "long"
                cnt = dr["cnt"]
                wins = dr["wins"]
                dir_metrics[f"{side}_trades"] = cnt
                dir_metrics[f"{side}_pnl"] = round(dr["pnl_sum"], 2)
                dir_metrics[f"{side}_win_rate"] = round(wins / cnt * 100, 1) if cnt > 0 else 0

            if metrics:
                metrics.update(dir_metrics)
        except Exception as e:
            log.warning(f"Error leyendo métricas direccionales: {e}")

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
    """Lista backtests del usuario."""
    params: list = [user["id"]]
    sql = """SELECT id, name, ticker, direction, date_from, date_to,
                    guardrails_config, models_config, models_enabled,
                    status, created_at, total_trades, pnl_total, pnl_pct,
                    win_rate, sharpe_ratio, equity_curve, max_drawdown
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
        """SELECT br.*, bm.total_trades, bm.pnl_total, bm.pnl_pct_total AS pnl_pct,
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
    """Serie temporal equity curve para chart (con trade_direction)."""
    rows = query(
        """SELECT equity_curve FROM backtest_runs
           WHERE id = %s AND (user_id = %s OR user_id IS NULL)""",
        [bt_id, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Backtest no encontrado")

    raw = rows[0].get("equity_curve")
    # Handle JSON string or list
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = []

    return {"equity_curve": raw or []}


@router.delete("/backtest/{bt_id}")
async def delete_backtest(bt_id: str, user: dict = Depends(get_current_user)):
    """Elimina un backtest guardado."""
    rows = query(
        "SELECT id, name FROM backtest_runs WHERE id = %s AND (user_id = %s OR user_id IS NULL)",
        [bt_id, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Backtest no encontrado o no tienes permiso")
    bt_name = rows[0]["name"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM backtest_trades WHERE backtest_name = %s", [bt_name])
                cur.execute("DELETE FROM backtest_metrics WHERE backtest_name = %s", [bt_name])
                cur.execute("DELETE FROM backtest_runs WHERE id = %s", [bt_id])
    except Exception as e:
        raise HTTPException(500, f"Error eliminando backtest: {e}") from e
    return {"deleted": True, "id": bt_id}
