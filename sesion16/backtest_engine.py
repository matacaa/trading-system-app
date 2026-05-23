"""
backtest.py — Sesión 16
───────────────────────
Backtester dual-dirección para ml-sandbox.

Simula operaciones LONG y SHORT sobre el test set usando modelos
entrenados y guardarraíles configurados en el yaml.

Flujo por cada barra (sin posición abierta):
    1. Evaluar guardrails comunes (horario, volumen, etc.)
    2. Ejecutar modelo → obtener P(subida)
    3. Evaluar path LONG:  guardrails LONG → P(subida) > umbral → LONG
    4. Evaluar path SHORT: guardrails SHORT → P(bajada) > umbral → SHORT
    5. Si ambos pasan → elegir el de mayor confianza

Reglas de gestión de posición:
    - LONG:  stop = entry * (1 - SL%), take = entry * (1 + TP%)
    - SHORT: stop = entry * (1 + SL%), take = entry * (1 - TP%)
    - Cierre fin de día si configurado
    - Si ambos SL y TP se tocan en misma vela → stop-loss (peor caso)

Genera equity_curve como lista de {date, value, direction?} para el frontend.

Uso:
    python -m apps.ml_sandbox.backtest --config config/backtests/aapl_backtest_v1.yaml
"""

from __future__ import annotations

import argparse
import json
import logging

import numpy as np
import pandas as pd
import yaml

from shared.db import execute, query, upsert
from shared.guardrails import check_guardrails_for_direction, check_score_for_direction
from shared.inference import load_models, predict_ensemble
from shared.utils.logging import setup_logging

log = logging.getLogger(__name__)


# ── Carga del yaml ────────────────────────────────────────────────────────────

def load_backtest_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Carga de datos silver ─────────────────────────────────────────────────────

def load_silver(cfg: dict) -> pd.DataFrame:
    """Carga silver_features del periodo de test para todos los tickers.
    Si context_tickers está definido, carga y une sus features con prefijo.
    """
    tickers = cfg["data"]["tickers"]
    context_tickers = cfg["data"].get("context_tickers", [])
    timeframe = cfg["data"].get("timeframe", "1m")
    table = f"silver_features_{timeframe}"
    start = cfg["data"]["test_start"]
    end = cfg["data"]["test_end"]
    end_plus = str(pd.Timestamp(end) + pd.Timedelta(days=1))

    all_dfs = []
    for ticker in tickers:
        rows = query(
            f"SELECT * FROM {table} "
            "WHERE ticker = %s AND ts >= %s AND ts < %s ORDER BY ts",
            [ticker, start, end_plus],
        )

        if rows:
            df = pd.DataFrame(rows)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            all_dfs.append(df)
            log.info(f"  {ticker}: {len(df)} velas cargadas")

    if not all_dfs:
        raise ValueError("No se encontraron datos silver para el periodo de test")

    result = pd.concat(all_dfs).sort_values(["ts", "ticker"]).reset_index(drop=True)

    # Context tickers
    if context_tickers:
        log.info(f"  Cargando context_tickers: {context_tickers}")
        ctx_feature_cols = [
            "ema_9", "ema_12", "ema_21", "rsi_14",
            "macd_line", "macd_signal", "bb_pct", "bb_width",
            "vwap", "atr_14", "returns_5", "volume_norm",
        ]
        ctx_select = ", ".join(["ts", "ticker"] + ctx_feature_cols)

        for ctx_ticker in context_tickers:
            rows = query(
                f"SELECT {ctx_select} FROM {table} "
                "WHERE ticker = %s AND ts >= %s AND ts < %s ORDER BY ts",
                [ctx_ticker, start, end_plus],
            )

            if not rows:
                log.warning(f"  context {ctx_ticker}: sin datos — omitiendo")
                continue

            ctx_df = pd.DataFrame(rows)
            ctx_df["ts"] = pd.to_datetime(ctx_df["ts"], utc=True)
            log.info(f"  context {ctx_ticker}: {len(ctx_df)} filas")

            rename_map = {c: f"{ctx_ticker}_{c}" for c in ctx_feature_cols if c in ctx_df.columns}
            ctx_df = ctx_df.rename(columns=rename_map)
            ctx_df = ctx_df.drop(columns=["ticker"], errors="ignore")
            result = result.merge(ctx_df, on="ts", how="left")

        ctx_cols = [c for c in result.columns if any(c.startswith(f"{t}_") for t in context_tickers)]
        if ctx_cols:
            result[ctx_cols] = result[ctx_cols].fillna(0)
            log.info(f"  Context features: {len(ctx_cols)} columnas añadidas")

    return result


# ── Funciones de posición ────────────────────────────────────────────────────

def _calc_pnl(entry: float, exit_price: float, qty: float, direction: str) -> float:
    """Calcula PnL según dirección."""
    if direction == "long":
        return (exit_price - entry) * qty
    else:  # short
        return (entry - exit_price) * qty


def _close_position(
    posicion: dict, precio_salida: float, ts, motivo: str, trades: list
) -> float:
    """Cierra una posición y registra el trade. Devuelve capital recuperado."""
    direction = posicion["direction"]
    pnl = _calc_pnl(posicion["precio_entrada"], precio_salida, posicion["qty"], direction)
    pnl_pct = (pnl / (posicion["precio_entrada"] * posicion["qty"])) * 100

    trades.append({
        "ticker": posicion["ticker"],
        "ts_entrada": posicion["ts_entrada"].isoformat(),
        "ts_salida": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        "precio_entrada": posicion["precio_entrada"],
        "precio_salida": precio_salida,
        "side": direction,
        "qty": posicion["qty"],
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "motivo_salida": motivo,
        "guardrail_motivo": "",
        "ejecutada": True,
    })

    if direction == "long":
        return posicion["qty"] * precio_salida
    else:
        # Short: devolvemos el margen + beneficio (o - pérdida)
        return posicion["margin"] + pnl


# ── Motor de backtest dual-dirección ──────────────────────────────────────────

def run_backtest_ticker(
    ticker: str,
    df: pd.DataFrame,
    modelos: list[dict],
    cfg: dict,
) -> tuple[list[dict], dict, list[dict]]:
    """
    Ejecuta el backtest dual-dirección para un ticker.

    Returns:
        trades:       lista de operaciones
        stats:        estadísticas del backtest
        equity_curve: serie temporal [{date, value, trade_direction?}]
    """
    cfg_capital = cfg["capital"]
    cfg_gr = cfg.get("guardrails", {})

    capital = cfg_capital["inicial"]
    posicion_max_pct = cfg_capital.get("posicion_max_pct", 10) / 100
    stop_loss_pct = cfg_capital.get("stop_loss_pct", 5) / 100
    take_profit_pct = cfg_capital.get("take_profit_pct", 10) / 100

    trades: list[dict] = []
    equity_curve: list[dict] = []
    posicion = None
    ordenes_hoy = 0
    dia_actual = None
    capital_max = capital
    gr_stats: dict[str, int] = {}

    has_models = len(modelos) > 0

    df_ticker = df[df["ticker"] == ticker].sort_values("ts").reset_index(drop=True)

    # Registrar punto inicial de equity
    if len(df_ticker) > 0:
        equity_curve.append({
            "date": df_ticker.iloc[0]["ts"].isoformat(),
            "value": round(capital, 2),
        })

    for _idx, row in df_ticker.iterrows():
        ts = row["ts"]
        dia = ts.date()

        # ── Nuevo día: reset órdenes + cierre forzado ──────────────
        if dia != dia_actual:
            if posicion and cfg_capital.get("cierre_fin_dia", True):
                precio_salida = posicion["last_close"]
                cap_back = _close_position(
                    posicion, precio_salida, ts, "cierre_fin_dia", trades
                )
                capital += cap_back
                capital_max = max(capital_max, capital)
                equity_curve.append({
                    "date": ts.isoformat(),
                    "value": round(capital, 2),
                    "trade_direction": posicion["direction"],
                })
                posicion = None

            dia_actual = dia
            ordenes_hoy = 0

        close = row.get("close", 0)
        high = row.get("high", 0)
        low = row.get("low", 0)

        # ── Gestionar posición abierta ─────────────────────────────
        if posicion:
            posicion["last_close"] = close
            cerrada = False
            precio_salida = None
            motivo_salida = None

            if posicion["direction"] == "long":
                # LONG: stop si low <= stop, take si high >= take
                hit_stop = low <= posicion["stop"]
                hit_take = high >= posicion["take"]
                if hit_stop and hit_take:
                    precio_salida = posicion["stop"]
                    motivo_salida = "stop_loss"
                    cerrada = True
                elif hit_stop:
                    precio_salida = posicion["stop"]
                    motivo_salida = "stop_loss"
                    cerrada = True
                elif hit_take:
                    precio_salida = posicion["take"]
                    motivo_salida = "take_profit"
                    cerrada = True
            else:
                # SHORT: stop si high >= stop, take si low <= take
                hit_stop = high >= posicion["stop"]
                hit_take = low <= posicion["take"]
                if hit_stop and hit_take:
                    precio_salida = posicion["stop"]
                    motivo_salida = "stop_loss"
                    cerrada = True
                elif hit_stop:
                    precio_salida = posicion["stop"]
                    motivo_salida = "stop_loss"
                    cerrada = True
                elif hit_take:
                    precio_salida = posicion["take"]
                    motivo_salida = "take_profit"
                    cerrada = True

            if cerrada:
                cap_back = _close_position(
                    posicion, precio_salida, ts, motivo_salida, trades
                )
                capital += cap_back
                capital_max = max(capital_max, capital)
                equity_curve.append({
                    "date": ts.isoformat(),
                    "value": round(capital, 2),
                    "trade_direction": posicion["direction"],
                })
                posicion = None
            else:
                continue  # Posición abierta, no evaluar nuevas señales

        # ── Sin posición: evaluar ambas direcciones ────────────────
        estado = {
            "posicion_abierta": False,
            "n_posiciones": 0,
            "ordenes_hoy": ordenes_hoy,
        }

        # Obtener score del modelo (si hay modelos cargados)
        score = 50.0  # neutral por defecto
        if has_models:
            df_hist_actual = df_ticker[df_ticker["ts"] <= ts].tail(10)
            score, _detalle, _ = predict_ensemble(row, modelos, df_hist=df_hist_actual)

        # ── Evaluar LONG ──────────────────────────────────────
        long_signal = False
        long_motivo = ""
        pasa_long, motivo_long = check_guardrails_for_direction(
            row, cfg_gr, estado, "long"
        )
        if pasa_long:
            pasa_score_long, motivo_score_long = check_score_for_direction(
                score, cfg_gr, "long"
            )
            if pasa_score_long:
                long_signal = True
            else:
                long_motivo = motivo_score_long
        else:
            long_motivo = motivo_long

        # ── Evaluar SHORT ─────────────────────────────────────
        short_signal = False
        short_motivo = ""
        pasa_short, motivo_short = check_guardrails_for_direction(
            row, cfg_gr, estado, "short"
        )
        if pasa_short:
            pasa_score_short, motivo_score_short = check_score_for_direction(
                score, cfg_gr, "short"
            )
            if pasa_score_short:
                short_signal = True
            else:
                short_motivo = motivo_score_short
        else:
            short_motivo = motivo_short

        # ── Decidir dirección ─────────────────────────────────
        chosen_direction = None
        if long_signal and short_signal:
            # Ambos pasan → elegir mayor confianza
            conf_long = score  # P(subida)
            conf_short = 100 - score  # P(bajada)
            chosen_direction = "long" if conf_long >= conf_short else "short"
        elif long_signal:
            chosen_direction = "long"
        elif short_signal:
            chosen_direction = "short"

        # ── Registrar señal rechazada o abrir posición ────────
        if chosen_direction is None:
            # Registrar el motivo del rechazo más relevante
            motivo = long_motivo or short_motivo or "sin_señal"
            gr_stats[motivo] = gr_stats.get(motivo, 0) + 1
            continue

        # ── Abrir posición ────────────────────────────────────
        qty = (capital * posicion_max_pct) / close
        coste = qty * close
        ordenes_hoy += 1

        if chosen_direction == "long":
            capital -= coste
            posicion = {
                "ticker": ticker,
                "direction": "long",
                "precio_entrada": close,
                "qty": qty,
                "ts_entrada": ts,
                "stop": close * (1 - stop_loss_pct),
                "take": close * (1 + take_profit_pct),
                "last_close": close,
                "margin": 0,
            }
        else:
            # SHORT: reservamos margen, no gastamos el capital completo
            margin = coste
            capital -= margin
            posicion = {
                "ticker": ticker,
                "direction": "short",
                "precio_entrada": close,
                "qty": qty,
                "ts_entrada": ts,
                "stop": close * (1 + stop_loss_pct),
                "take": close * (1 - take_profit_pct),
                "last_close": close,
                "margin": margin,
            }

        trades.append({
            "ticker": ticker,
            "ts_entrada": ts.isoformat(),
            "ts_salida": None,
            "precio_entrada": close,
            "precio_salida": None,
            "side": chosen_direction,
            "qty": round(qty, 4),
            "pnl": 0,
            "pnl_pct": 0,
            "motivo_salida": "abierta",
            "guardrail_motivo": "",
            "ejecutada": True,
        })

    # ── Cierre final si quedó posición abierta ───────────────────
    if posicion:
        precio_salida = posicion["last_close"]
        cap_back = _close_position(
            posicion, precio_salida,
            df_ticker.iloc[-1]["ts"] if len(df_ticker) > 0 else "end",
            "cierre_final", trades
        )
        capital += cap_back
        capital_max = max(capital_max, capital)

    # ── Estadísticas separadas por dirección ─────────────────────
    trades_cerrados = [
        t for t in trades
        if t["ejecutada"] and t["motivo_salida"] not in ("abierta",)
    ]
    long_trades = [t for t in trades_cerrados if t["side"] == "long"]
    short_trades = [t for t in trades_cerrados if t["side"] == "short"]

    def _calc_stats(subset: list[dict], label: str) -> dict:
        n = len(subset)
        n_wins = sum(1 for t in subset if t["pnl"] > 0)
        pnl_total = sum(t["pnl"] for t in subset)
        return {
            f"{label}_trades": n,
            f"{label}_wins": n_wins,
            f"{label}_losses": n - n_wins,
            f"{label}_win_rate": round(n_wins / n * 100, 1) if n > 0 else 0,
            f"{label}_pnl": round(pnl_total, 2),
        }

    n_total = len(trades_cerrados)
    n_wins_total = sum(1 for t in trades_cerrados if t["pnl"] > 0)
    pnl_total = sum(t["pnl"] for t in trades_cerrados)

    retornos = [t["pnl_pct"] / 100 for t in trades_cerrados if t["pnl"] != 0]
    sharpe = 0.0
    if retornos and np.std(retornos) > 0:
        n_days = max(1, len({t.get("ts_entrada", "")[:10] for t in trades_cerrados}))
        trades_per_day = len(retornos) / n_days if n_days > 0 else 1
        annualization_factor = np.sqrt(252 * trades_per_day)
        sharpe = round(np.mean(retornos) / np.std(retornos) * annualization_factor, 2)

    # Max drawdown
    peak = cfg_capital["inicial"]
    drawdown = 0.0
    running = cfg_capital["inicial"]
    for t in trades_cerrados:
        if t["pnl"] != 0:
            running += t["pnl"]
            peak = max(peak, running)
            drawdown = max(drawdown, (peak - running) / peak * 100)

    stats = {
        "capital_inicial": cfg_capital["inicial"],
        "capital_final": round(capital, 2),
        "pnl_total": round(pnl_total, 2),
        "pnl_pct_total": round(pnl_total / cfg_capital["inicial"] * 100, 2),
        "n_trades": n_total,
        "n_wins": n_wins_total,
        "n_losses": n_total - n_wins_total,
        "win_rate": round(n_wins_total / n_total * 100, 1) if n_total > 0 else 0,
        "sharpe_ratio": sharpe,
        "max_drawdown": round(drawdown, 2),
        "guardrail_stats": gr_stats,
        **_calc_stats(long_trades, "long"),
        **_calc_stats(short_trades, "short"),
    }

    # Equity curve final point
    if equity_curve and equity_curve[-1]["value"] != round(capital, 2):
        equity_curve.append({
            "date": equity_curve[-1]["date"],
            "value": round(capital, 2),
        })

    return trades, stats, equity_curve


# ── Guardado en PostgreSQL ──────────────────────────────────────────────────

def save_results(
    cfg: dict, trades: list[dict], stats: dict, equity_curve: list[dict]
) -> None:
    """Guarda resultados en PostgreSQL."""
    name = cfg["backtest"]["name"]

    trades_rows = [{"backtest_name": name, **t} for t in trades]
    metrics_row = {
        "backtest_name": name,
        "capital_final": stats["capital_final"],
        "pnl_total": stats["pnl_total"],
        "pnl_pct_total": stats["pnl_pct_total"],
        "total_trades": stats["n_trades"],
        "n_trades": stats["n_trades"],
        "n_wins": stats["n_wins"],
        "n_losses": stats["n_losses"],
        "win_rate": stats["win_rate"],
        "sharpe_ratio": stats["sharpe_ratio"],
        "max_drawdown": stats["max_drawdown"],
        "guardrail_stats": json.dumps(stats["guardrail_stats"]),
        "long_trades": stats.get("long_trades", 0),
        "long_pnl": stats.get("long_pnl", 0),
        "long_win_rate": stats.get("long_win_rate", 0),
        "short_trades": stats.get("short_trades", 0),
        "short_pnl": stats.get("short_pnl", 0),
        "short_win_rate": stats.get("short_win_rate", 0),
    }

    try:
        # Paso 1: borrar datos anteriores
        execute("DELETE FROM backtest_trades WHERE backtest_name = %s", [name])
        execute("DELETE FROM backtest_metrics WHERE backtest_name = %s", [name])

        # Paso 2: insertar trades en batches
        inserted = 0
        failed_batches = 0
        for i in range(0, len(trades_rows), 100):
            batch = trades_rows[i : i + 100]
            try:
                upsert("backtest_trades", batch, conflict="backtest_name,ts_entrada,ticker")
                inserted += len(batch)
            except Exception as e:
                failed_batches += 1
                log.error(f"  Error batch {i // 100 + 1}: {e} ({len(batch)} trades perdidos)")

        if failed_batches:
            log.warning(
                f"  {failed_batches} batches fallaron. "
                f"{inserted}/{len(trades_rows)} trades guardados."
            )

        # Paso 3: insertar metrics
        execute(
            """INSERT INTO backtest_metrics
               (backtest_name, capital_final, pnl_total, pnl_pct_total,
                total_trades, n_trades, n_wins, n_losses, win_rate,
                sharpe_ratio, max_drawdown, guardrail_stats)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [name, metrics_row["capital_final"], metrics_row["pnl_total"],
             metrics_row["pnl_pct_total"], metrics_row["total_trades"],
             metrics_row["n_trades"], metrics_row["n_wins"],
             metrics_row["n_losses"], metrics_row["win_rate"],
             metrics_row["sharpe_ratio"], metrics_row["max_drawdown"],
             metrics_row["guardrail_stats"]],
        )

        log.info(f"Resultados guardados: {name}")

    except Exception as e:
        log.error(f"Error fatal guardando backtest '{name}': {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ML Sandbox Backtester")
    parser.add_argument("--config", required=True, help="Ruta al backtest yaml")
    args = parser.parse_args()

    setup_logging(app_name="backtest")

    cfg = load_backtest_config(args.config)
    name = cfg["backtest"]["name"]

    log.info(f"Iniciando backtest dual-dirección: {name}")
    log.info(f"Periodo: {cfg['data']['test_start']} -> {cfg['data']['test_end']}")
    log.info(f"Tickers: {cfg['data']['tickers']}")

    log.info("Cargando datos silver...")
    df = load_silver(cfg)

    log.info("Cargando modelos...")
    modelos = load_models(cfg["modelos"])
    if not modelos:
        log.warning(
            "No se pudieron cargar modelos del registry. "
            "El backtest se ejecutará solo con guardrails (score=50 neutral)."
        )

    all_trades: list[dict] = []
    all_stats: dict[str, dict] = {}
    all_equity: list[dict] = []

    for ticker in cfg["data"]["tickers"]:
        log.info(f"Backtesting {ticker}...")
        trades, stats, equity = run_backtest_ticker(ticker, df, modelos, cfg)
        all_trades.extend(trades)
        all_stats[ticker] = stats
        all_equity.extend(equity)

        log.info(f"  P&L: {stats['pnl_total']:+.2f} ({stats['pnl_pct_total']:+.2f}%)")
        log.info(f"  Trades: {stats['n_trades']} (L:{stats['long_trades']} S:{stats['short_trades']})")
        log.info(f"  Win rate: {stats['win_rate']}% (L:{stats['long_win_rate']}% S:{stats['short_win_rate']}%)")
        log.info(f"  Sharpe: {stats['sharpe_ratio']} | Drawdown: {stats['max_drawdown']}%")

    # Combinar stats multi-ticker
    if len(all_stats) == 1:
        stats_combined = list(all_stats.values())[0]
    else:
        stats_combined = {
            "capital_inicial": cfg["capital"]["inicial"],
            "capital_final": round(sum(s["capital_final"] for s in all_stats.values()), 2),
            "pnl_total": round(sum(s["pnl_total"] for s in all_stats.values()), 2),
            "pnl_pct_total": round(sum(s["pnl_pct_total"] for s in all_stats.values()) / len(all_stats), 2),
            "n_trades": sum(s["n_trades"] for s in all_stats.values()),
            "n_wins": sum(s["n_wins"] for s in all_stats.values()),
            "n_losses": sum(s["n_losses"] for s in all_stats.values()),
            "win_rate": round(sum(s["win_rate"] for s in all_stats.values()) / len(all_stats), 1),
            "sharpe_ratio": round(sum(s["sharpe_ratio"] for s in all_stats.values()) / len(all_stats), 2),
            "max_drawdown": round(max(s["max_drawdown"] for s in all_stats.values()), 2),
            "guardrail_stats": {k: v for s in all_stats.values() for k, v in s["guardrail_stats"].items()},
            "long_trades": sum(s.get("long_trades", 0) for s in all_stats.values()),
            "long_pnl": round(sum(s.get("long_pnl", 0) for s in all_stats.values()), 2),
            "long_win_rate": round(sum(s.get("long_win_rate", 0) for s in all_stats.values()) / len(all_stats), 1),
            "long_wins": sum(s.get("long_wins", 0) for s in all_stats.values()),
            "long_losses": sum(s.get("long_losses", 0) for s in all_stats.values()),
            "short_trades": sum(s.get("short_trades", 0) for s in all_stats.values()),
            "short_pnl": round(sum(s.get("short_pnl", 0) for s in all_stats.values()), 2),
            "short_win_rate": round(sum(s.get("short_win_rate", 0) for s in all_stats.values()) / len(all_stats), 1),
            "short_wins": sum(s.get("short_wins", 0) for s in all_stats.values()),
            "short_losses": sum(s.get("short_losses", 0) for s in all_stats.values()),
        }

    log.info("Guardando resultados...")
    save_results(cfg, all_trades, stats_combined, all_equity)
    log.info(f"Backtest completado: {name}")


if __name__ == "__main__":
    main()
