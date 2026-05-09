"""
reconciliation.py
─────────────────
Resuelve F-39: gold_trades nunca se actualizaba al fill ni al cierre.

Consulta Alpaca para cada trade abierto (ts_salida IS NULL),
detecta fills, cierres de legs (SL/TP), y actualiza gold_trades con:
    - precio_entrada real (fill, no ask_price — F-38)
    - ts_salida, precio_salida, pnl, pnl_pct, motivo_salida, status

Uso:
    from apps.trading_engine.reconciliation import reconcile_trades
    n = reconcile_trades()  # retorna número de trades actualizados

Diseñado para correr periódicamente (cada iteración del pipeline o cron).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from shared.db import sb
from shared.utils.time import utc_isoformat
from apps.trading_engine.alpaca_trader import _get_trading_client

log = logging.getLogger(__name__)

# Status de Alpaca que indican cierre
_CLOSED_STATUSES = {"filled", "canceled", "expired", "done_for_day", "replaced"}


def _get_open_trades() -> list[dict]:
    """Lee trades sin ts_salida de gold_trades."""
    try:
        resp = (
            sb.table("gold_trades")
            .select("id, ticker, alpaca_order_id, precio_entrada, qty, ts_entrada")
            .is_("ts_salida", "null")
            .not_.is_("alpaca_order_id", "null")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        log.error(f"Error leyendo trades abiertos: {e}")
        return []


def _normalize_status(status) -> str:
    """Convierte OrderStatus enum o string 'OrderStatus.X' a string limpio."""
    s = str(status)
    if s.startswith("OrderStatus."):
        s = s.replace("OrderStatus.", "")
    return s.lower()


def _reconcile_one(trade: dict, client: TradingClient) -> dict | None:
    """
    Consulta Alpaca para un trade y determina si se cerró.

    Returns:
        dict con campos a actualizar en gold_trades, o None si sigue abierto.
    """
    order_id = trade["alpaca_order_id"]
    ticker = trade["ticker"]

    try:
        order = client.get_order_by_id(order_id)
    except Exception as e:
        log.warning(f"  {ticker}: no se pudo consultar order {order_id}: {e}")
        return None

    parent_status = _normalize_status(order.status)

    # ─── Actualizar precio_entrada con fill real (F-38) ─────────
    update: dict = {"status": parent_status}

    if order.filled_avg_price and float(order.filled_avg_price) > 0:
        fill_price = float(order.filled_avg_price)
        if fill_price != trade["precio_entrada"]:
            log.info(
                f"  {ticker}: precio_entrada corregido "
                f"{trade['precio_entrada']} → {fill_price} (fill real)"
            )
            update["precio_entrada"] = fill_price

    # ─── Si el parent no está filled, comprobar cancelación ─────
    if parent_status in ("canceled", "expired", "done_for_day"):
        log.info(f"  {ticker}: order {parent_status}")
        update.update({
            "ts_salida": order.canceled_at.isoformat() if order.canceled_at else utc_isoformat(),
            "precio_salida": trade["precio_entrada"],
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "motivo_salida": parent_status,
        })
        return update

    if parent_status != "filled":
        # Sigue pendiente (new, accepted, partially_filled, pending_new...)
        return update if "precio_entrada" in update else None

    # ─── Parent filled — revisar legs (SL/TP) ──────────────────
    legs = order.legs or []

    for leg in legs:
        leg_status = _normalize_status(leg.status)

        if leg_status != "filled":
            continue

        # Este leg se ejecutó — es la salida
        precio_salida = float(leg.filled_avg_price) if leg.filled_avg_price else 0
        ts_salida = leg.filled_at.isoformat() if leg.filled_at else utc_isoformat()

        # Determinar motivo por tipo de leg
        leg_type = str(getattr(leg, "order_type", "")).lower()
        if "stop" in leg_type:
            motivo = "stop_loss"
        elif "limit" in leg_type:
            motivo = "take_profit"
        else:
            motivo = "leg_filled"

        # Calcular P&L
        entrada = update.get("precio_entrada", trade["precio_entrada"])
        qty = trade["qty"]
        pnl = (precio_salida - entrada) * qty
        pnl_pct = (precio_salida / entrada - 1) * 100 if entrada > 0 else 0

        log.info(
            f"  {ticker}: {motivo} @ {precio_salida} | "
            f"P&L: {pnl:+.2f} ({pnl_pct:+.2f}%)"
        )

        update.update({
            "ts_salida": ts_salida,
            "precio_salida": precio_salida,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "motivo_salida": motivo,
        })
        return update

    # Parent filled pero legs aún abiertos — SL/TP pendientes
    log.info(f"  {ticker}: parent filled, legs aún activos")
    return update if update != {"status": parent_status} else None


def reconcile_trades() -> int:
    """
    Revisa todos los trades abiertos y actualiza los que hayan cerrado.
    También detecta cierres manuales: si un trade está abierto en gold_trades
    pero la posición ya no existe en Alpaca, se marca como cerrado.

    Returns:
        Número de trades actualizados.
    """
    open_trades = _get_open_trades()

    if not open_trades:
        log.info("Reconciliation: sin trades abiertos")
        return 0

    log.info(f"Reconciliation: {len(open_trades)} trades abiertos")
    client = _get_trading_client()
    updated = 0

    # Get current Alpaca positions to detect manual closes
    try:
        positions = client.get_all_positions()
        open_tickers = {p.symbol for p in positions}
    except Exception as e:
        log.warning(f"  No se pudieron obtener posiciones de Alpaca: {e}")
        open_tickers = None  # Skip manual close detection

    for trade in open_trades:
        result = _reconcile_one(trade, client)

        # If normal reconciliation found nothing, check for manual close
        if result is None and open_tickers is not None:
            ticker = trade["ticker"]
            if ticker not in open_tickers:
                log.info(f"  {ticker}: posición no existe en Alpaca — cierre manual detectado")
                result = {
                    "ts_salida": utc_isoformat(),
                    "precio_salida": trade["precio_entrada"],  # Best estimate
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                    "motivo_salida": "cierre_manual_alpaca",
                    "status": "closed",
                }

        if result is None:
            continue

        try:
            sb.table("gold_trades").update(result).eq("id", trade["id"]).execute()
            updated += 1
        except Exception as e:
            log.error(f"  Error actualizando trade {trade['id']}: {e}")

    log.info(f"Reconciliation completada: {updated}/{len(open_trades)} actualizados")
    return updated