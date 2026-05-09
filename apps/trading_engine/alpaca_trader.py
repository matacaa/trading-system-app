"""
alpaca_trader.py
────────────────
Ejecuta órdenes bracket en Alpaca paper trading.
Stop-loss y take-profit automáticos via bracket order.

Cambios respecto al original:
    - F-33: un solo TradingClient reutilizado (antes creaba 3 por orden)
    - F-42: gold_trades se inserta con todos los campos (ts_salida, pnl, etc.)
    - F-28/F-41: get_orders_today usa fecha ET (antes usaba UTC/local)
    - Credenciales vienen de shared.config.cfg

Uso:
    from apps.trading_engine.alpaca_trader import execute_order, close_all
"""

from __future__ import annotations

import logging
from functools import lru_cache

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce

from shared.config import cfg
from shared.db import sb
from shared.utils.time import now_utc, today_et, utc_isoformat

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_trading_client() -> TradingClient:
    """Cliente Alpaca singleton (F-33: antes se creaban 3 por orden)."""
    return TradingClient(
        api_key=cfg.alpaca_api_key,
        secret_key=cfg.alpaca_secret_key,
        paper=cfg.alpaca_paper,
    )


@lru_cache(maxsize=1)
def _get_data_client():
    """N-04: Cliente de datos Alpaca singleton."""
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)


def get_portfolio_state() -> dict:
    """
    Obtiene el estado actual del portfolio en Alpaca.

    Returns:
        dict con capital, posiciones abiertas, n_posiciones
    """
    try:
        client = _get_trading_client()
        account = client.get_account()
        positions = client.get_all_positions()

        posiciones = {
            p.symbol: {
                "qty": float(p.qty),
                "precio_entrada": float(p.avg_entry_price),
                "valor_actual": float(p.market_value),
                "pnl": float(p.unrealized_pl),
            }
            for p in positions
        }

        return {
            "capital": float(account.cash),
            "posiciones": posiciones,
            "n_posiciones": len(posiciones),
            "portfolio_value": float(account.portfolio_value),
        }

    except Exception as e:
        log.error(
            f"Error obteniendo estado del portfolio: {e}. "
            f"El bot NO operará hasta que se resuelva este error."
        )
        return {
            "capital": 0,
            "posiciones": {},
            "n_posiciones": 0,
            "portfolio_value": 0,
            "error": True,  # F-34: flag para que el caller sepa que falló
        }


def get_orders_today() -> int:
    """Cuenta las órdenes ejecutadas hoy (en ET, no UTC — F-28/F-41)."""
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        from datetime import datetime

        client = _get_trading_client()
        # F-28/F-41: usar fecha ET para que el día de trading sea correcto
        hoy_et = today_et()
        request = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            after=datetime.combine(hoy_et, datetime.min.time()).isoformat(),
        )
        orders = client.get_orders(request)
        return len(orders)
    except Exception as e:
        log.error(f"Error contando órdenes de hoy: {e}")
        return 0


def execute_order(
    ticker: str,
    decision: dict,
    cfg_capital: dict,
    estado: dict,
) -> dict | None:
    """
    Ejecuta una orden bracket en Alpaca.

    Returns:
        dict con datos de la orden ejecutada o None si falla
    """
    if decision.get("decision") != "BUY":
        return None

    try:
        client = _get_trading_client()

        # Obtener precio actual (N-04: usa singleton)
        from alpaca.data.requests import StockLatestQuoteRequest

        data_client = _get_data_client()
        quote_req = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
        quote = data_client.get_stock_latest_quote(quote_req)
        precio = float(quote[ticker].ask_price)

        if precio <= 0:
            log.warning(f"  {ticker}: precio inválido ({precio})")
            return None

        # Calcular cantidad — bracket orders requieren qty entera (no fraccional)
        capital = estado.get("capital", cfg_capital["inicial"])
        posicion_max_pct = cfg_capital.get("posicion_max_pct", 10) / 100
        stop_loss_pct = cfg_capital.get("stop_loss_pct", 5) / 100
        take_profit_pct = cfg_capital.get("take_profit_pct", 10) / 100

        import math
        qty = math.floor((capital * posicion_max_pct) / precio)

        if qty < 1:
            log.warning(f"  {ticker}: qty < 1 — capital insuficiente para 1 acción (precio={precio})")
            return None

        stop_price = round(precio * (1 - stop_loss_pct), 2)
        take_price = round(precio * (1 + take_profit_pct), 2)

        # F-37: SL/TP se calculan sobre ask_price (no fill).
        # Reconciliation corregirá precio_entrada al fill real.
        log.info(
            f"  {ticker}: BUY {qty} @ ~{precio} | SL {stop_price} ({stop_loss_pct:.0%}) | TP {take_price} ({take_profit_pct:.0%})"
        )

        # Crear bracket order
        order_request = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class="bracket",
            take_profit=TakeProfitRequest(limit_price=take_price),
            stop_loss=StopLossRequest(stop_price=stop_price),
        )

        order = client.submit_order(order_request)

        # F-42: insertar con TODOS los campos (antes faltaban ts_salida, pnl, etc.)
        trade = {
            "ticker": ticker,
            "ts_entrada": utc_isoformat(),
            "ts_salida": None,
            "side": "buy",
            "qty": float(qty),
            "precio_entrada": precio,
            "precio_salida": None,
            "stop_loss": stop_price,
            "take_profit": take_price,
            "pnl": None,
            "pnl_pct": None,
            "motivo_salida": None,
            "alpaca_order_id": str(order.id),
            "status": str(order.status),
            "run_at": utc_isoformat(),
        }

        sb.table("gold_trades").insert(trade).execute()
        log.info(f"  {ticker}: orden ejecutada — ID {order.id}")
        return trade

    except Exception as e:
        log.error(f"  Error ejecutando orden {ticker}: {e}")
        return None


def close_all() -> None:
    """Cierra todas las posiciones abiertas — función de emergencia.
    F-40: ahora actualiza gold_trades para cada posición cerrada.
    I-03: incluye precio_salida y P&L calculado desde datos de la posición.
    """
    try:
        client = _get_trading_client()

        # Leer posiciones antes de cerrar para poder actualizar gold_trades
        positions = client.get_all_positions()
        position_data = {
            p.symbol: {
                "current_price": float(p.current_price) if p.current_price else 0,
                "avg_entry_price": float(p.avg_entry_price) if p.avg_entry_price else 0,
                "qty": float(p.qty) if p.qty else 0,
                "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else 0,
                "unrealized_plpc": float(p.unrealized_plpc) * 100 if p.unrealized_plpc else 0,
            }
            for p in positions
        }
        tickers_cerrados = list(position_data.keys())

        client.close_all_positions(cancel_orders=True)
        log.info(f"Todas las posiciones cerradas: {tickers_cerrados}")

        # F-40 + I-03: actualizar gold_trades con P&L real
        for ticker, pos in position_data.items():
            try:
                sb.table("gold_trades").update({
                    "ts_salida": utc_isoformat(),
                    "precio_salida": pos["current_price"],
                    "pnl": round(pos["unrealized_pl"], 2),
                    "pnl_pct": round(pos["unrealized_plpc"], 2),
                    "motivo_salida": "close_all_emergencia",
                    "status": "closed",
                }).eq("ticker", ticker).is_("ts_salida", "null").execute()
            except Exception as e:
                log.warning(f"  Error actualizando gold_trades para {ticker}: {e}")

    except Exception as e:
        log.error(f"Error cerrando posiciones: {e}")