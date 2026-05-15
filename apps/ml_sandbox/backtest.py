"""
backtest.py
───────────
Backtester completo para ml-sandbox.

Simula operaciones sobre el test set usando los modelos entrenados
y los guardarraíles configurados en el yaml.

Reglas:
    - Ninguna posición puede quedar abierta al cierre del día
    - Stop-loss y take-profit se evalúan vela a vela con high/low
    - Si ambos se tocan en la misma vela se asume stop-loss (peor caso)

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

from shared.db import sb
from shared.guardrails import check_guardrails
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

    all_dfs = []
    for ticker in tickers:
        rows: list[dict] = []
        offset = 0
        while True:
            resp = (
                sb.table(table)
                .select("*")
                .eq("ticker", ticker)
                .gte("ts", start)
                .lt("ts", str(pd.Timestamp(end) + pd.Timedelta(days=1)))
                .order("ts")
                .range(offset, offset + 999)
                .execute()
            )
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

        if rows:
            df = pd.DataFrame(rows)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            all_dfs.append(df)
            log.info(f"  {ticker}: {len(df)} velas cargadas")

    if not all_dfs:
        raise ValueError("No se encontraron datos silver para el periodo de test")

    result = pd.concat(all_dfs).sort_values(["ts", "ticker"]).reset_index(drop=True)

    # Context tickers: cargar features y unir por timestamp
    if context_tickers:
        log.info(f"  Cargando context_tickers: {context_tickers}")
        # Columnas de features a usar como contexto
        ctx_feature_cols = [
            "ema_9", "ema_12", "ema_21", "rsi_14",
            "macd_line", "macd_signal", "bb_pct", "bb_width",
            "vwap", "atr_14", "returns_5", "volume_norm",
        ]
        ctx_select = ",".join(["ts", "ticker"] + ctx_feature_cols)

        for ctx_ticker in context_tickers:
            rows: list[dict] = []
            offset = 0
            while True:
                resp = (
                    sb.table(table)
                    .select(ctx_select)
                    .eq("ticker", ctx_ticker)
                    .gte("ts", start)
                    .lt("ts", str(pd.Timestamp(end) + pd.Timedelta(days=1)))
                    .order("ts")
                    .range(offset, offset + 999)
                    .execute()
                )
                batch = resp.data or []
                rows.extend(batch)
                if len(batch) < 1000:
                    break
                offset += 1000

            if not rows:
                log.warning(f"  context {ctx_ticker}: sin datos — omitiendo")
                continue

            ctx_df = pd.DataFrame(rows)
            ctx_df["ts"] = pd.to_datetime(ctx_df["ts"], utc=True)
            log.info(f"  context {ctx_ticker}: {len(ctx_df)} filas")

            # Renombrar con prefijo
            rename_map = {c: f"{ctx_ticker}_{c}" for c in ctx_feature_cols if c in ctx_df.columns}
            ctx_df = ctx_df.rename(columns=rename_map)
            ctx_df = ctx_df.drop(columns=["ticker"], errors="ignore")

            # Merge por timestamp
            result = result.merge(ctx_df, on="ts", how="left")

        # Rellenar NaN de context con 0
        ctx_cols = [c for c in result.columns if any(c.startswith(f"{t}_") for t in context_tickers)]
        if ctx_cols:
            result[ctx_cols] = result[ctx_cols].fillna(0)
            log.info(f"  Context features: {len(ctx_cols)} columnas añadidas")

    return result


# ── Motor de backtest ─────────────────────────────────────────────────────────

def run_backtest_ticker(
    ticker: str,
    df: pd.DataFrame,
    modelos: list[dict],
    cfg: dict,
) -> tuple[list[dict], dict]:
    """
    Ejecuta el backtest para un ticker.

    Returns:
        trades: lista de operaciones
        stats:  estadísticas del backtest
    """
    cfg_capital = cfg["capital"]
    cfg_gr = cfg.get("guardrails", {})

    capital = cfg_capital["inicial"]
    posicion_max_pct = cfg_capital.get("posicion_max_pct", 10) / 100
    stop_loss_pct = cfg_capital.get("stop_loss_pct", 5) / 100
    take_profit_pct = cfg_capital.get("take_profit_pct", 10) / 100

    trades: list[dict] = []
    posicion = None
    ordenes_hoy = 0
    dia_actual = None
    capital_max = capital
    gr_stats: dict[str, int] = {}

    df_ticker = df[df["ticker"] == ticker].sort_values("ts").reset_index(drop=True)

    for idx, row in df_ticker.iterrows():
        ts = row["ts"]
        dia = ts.date()

        # Nuevo día — reset órdenes y cierre forzado
        if dia != dia_actual:
            if posicion and cfg_capital.get("cierre_fin_dia", True):
                precio_salida = posicion["last_close"]
                pnl = (precio_salida - posicion["precio_entrada"]) * posicion["qty"]
                pnl_pct = (precio_salida / posicion["precio_entrada"] - 1) * 100
                capital += posicion["qty"] * precio_salida
                capital_max = max(capital_max, capital)  # N-11: también en cierre fin de día
                trades.append({
                    "ticker": ticker,
                    "ts_entrada": posicion["ts_entrada"].isoformat(),
                    "ts_salida": ts.isoformat(),
                    "precio_entrada": posicion["precio_entrada"],
                    "precio_salida": precio_salida,
                    "side": "buy",
                    "qty": posicion["qty"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "motivo_salida": "cierre_fin_dia",
                    "guardrail_motivo": "",
                    "ejecutada": True,
                })
                posicion = None

            dia_actual = dia
            ordenes_hoy = 0

        close = row.get("close", 0)
        high = row.get("high", 0)
        low = row.get("low", 0)

        # Gestionar posición abierta
        if posicion:
            posicion["last_close"] = close
            cerrada = False
            precio_salida = None
            motivo_salida = None

            # Si ambos se tocan en la misma vela → stop-loss (peor caso)
            if low <= posicion["stop"] and high >= posicion["take"]:
                precio_salida = posicion["stop"]
                motivo_salida = "stop_loss"
                cerrada = True
            elif low <= posicion["stop"]:
                precio_salida = posicion["stop"]
                motivo_salida = "stop_loss"
                cerrada = True
            elif high >= posicion["take"]:
                precio_salida = posicion["take"]
                motivo_salida = "take_profit"
                cerrada = True

            if cerrada:
                pnl = (precio_salida - posicion["precio_entrada"]) * posicion["qty"]
                pnl_pct = (precio_salida / posicion["precio_entrada"] - 1) * 100
                capital += posicion["qty"] * precio_salida
                capital_max = max(capital_max, capital)
                trades.append({
                    "ticker": ticker,
                    "ts_entrada": posicion["ts_entrada"].isoformat(),
                    "ts_salida": ts.isoformat(),
                    "precio_entrada": posicion["precio_entrada"],
                    "precio_salida": precio_salida,
                    "side": "buy",
                    "qty": posicion["qty"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "motivo_salida": motivo_salida,
                    "guardrail_motivo": "",
                    "ejecutada": True,
                })
                posicion = None
            else:
                continue

        # Sin posición — evaluar si abrir
        df_hist_actual = df_ticker[df_ticker["ts"] <= ts].tail(10)
        score, detalle, _ = predict_ensemble(row, modelos, df_hist=df_hist_actual)

        # F-21: score threshold configurable desde yaml
        score_threshold = cfg_gr.get("score_threshold", 50)

        estado = {
            "posicion_abierta": posicion is not None,
            "n_posiciones": 1 if posicion else 0,
            "ordenes_hoy": ordenes_hoy,
        }

        pasa, motivo = check_guardrails(row, score, cfg_gr, estado)

        if not pasa:
            gr_stats[motivo] = gr_stats.get(motivo, 0) + 1
            trades.append({
                "ticker": ticker,
                "ts_entrada": ts.isoformat(),
                "ts_salida": None,
                "precio_entrada": close,
                "precio_salida": None,
                "side": "buy",
                "qty": 0,
                "pnl": 0,
                "pnl_pct": 0,
                "motivo_salida": "guardrail",
                "guardrail_motivo": motivo,
                "ejecutada": False,
            })
            continue

        # Abrir posición si score >= threshold (F-21: configurable)
        if score >= score_threshold:
            qty = (capital * posicion_max_pct) / close
            coste = qty * close
            capital -= coste
            ordenes_hoy += 1
            posicion = {
                "precio_entrada": close,
                "qty": qty,
                "ts_entrada": ts,
                "stop": close * (1 - stop_loss_pct),
                "take": close * (1 + take_profit_pct),
                "last_close": close,
            }
            trades.append({
                "ticker": ticker,
                "ts_entrada": ts.isoformat(),
                "ts_salida": None,
                "precio_entrada": close,
                "precio_salida": None,
                "side": "buy",
                "qty": round(qty, 4),
                "pnl": 0,
                "pnl_pct": 0,
                "motivo_salida": "abierta",
                "guardrail_motivo": "",
                "ejecutada": True,
            })

    # ── Estadísticas ──────────────────────────────────────────────
    capital_curve = [cfg_capital["inicial"]]
    running = cfg_capital["inicial"]
    for t in trades:
        if t["ejecutada"] and t["pnl"] != 0:
            running += t["pnl"]
            capital_curve.append(running)

    peak = capital_curve[0]
    drawdown = 0.0
    for c in capital_curve:
        peak = max(peak, c)
        drawdown = max(drawdown, (peak - c) / peak * 100)

    trades_cerrados = [
        t for t in trades
        if t["ejecutada"] and t["motivo_salida"] not in ("abierta",)
    ]
    n_trades = len(trades_cerrados)
    n_wins = sum(1 for t in trades_cerrados if t["pnl"] > 0)
    n_losses = sum(1 for t in trades_cerrados if t["pnl"] <= 0)
    pnl_total = sum(t["pnl"] for t in trades_cerrados)

    retornos = [t["pnl_pct"] / 100 for t in trades_cerrados if t["pnl"] != 0]
    sharpe = 0.0
    if retornos and np.std(retornos) > 0:
        # F-01: anualización correcta para intraday.
        # n_trades / n_trading_days = trades por día. Anualizamos con sqrt(252 * trades_por_día).
        n_days = max(1, len(set(t.get("ts_entrada", "")[:10] for t in trades_cerrados)))
        trades_per_day = len(retornos) / n_days if n_days > 0 else 1
        annualization_factor = np.sqrt(252 * trades_per_day)
        sharpe = round(np.mean(retornos) / np.std(retornos) * annualization_factor, 2)

    stats = {
        "capital_inicial": cfg_capital["inicial"],
        "capital_final": round(capital, 2),
        "pnl_total": round(pnl_total, 2),
        "pnl_pct_total": round(pnl_total / cfg_capital["inicial"] * 100, 2),
        "n_trades": n_trades,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": round(n_wins / n_trades * 100, 1) if n_trades > 0 else 0,
        "sharpe_ratio": sharpe,
        "max_drawdown": round(drawdown, 2),
        "guardrail_stats": gr_stats,
    }

    return trades, stats


# ── Guardado en Supabase ──────────────────────────────────────────────────────

def save_results(cfg: dict, trades: list[dict], stats: dict) -> None:
    """Guarda resultados en Supabase.
    F-03: primero inserta en tabla temporal, luego borra los viejos.
    F-04: tracking de batches fallidos.
    """
    name = cfg["backtest"]["name"]

    # F-03: intentar insertar primero. Si falla, no borramos los viejos.
    trades_rows = [{"backtest_name": name, **t} for t in trades]

    metrics_row = {
        "backtest_name": name,
        "capital_final": stats["capital_final"],
        "pnl_total": stats["pnl_total"],
        "pnl_pct_total": stats["pnl_pct_total"],
        "n_trades": stats["n_trades"],
        "n_wins": stats["n_wins"],
        "n_losses": stats["n_losses"],
        "win_rate": stats["win_rate"],
        "sharpe_ratio": stats["sharpe_ratio"],
        "max_drawdown": stats["max_drawdown"],
        "guardrail_stats": json.dumps(stats["guardrail_stats"]),
    }

    run_row = {
        "name": name,
        "tickers": json.dumps(cfg["data"]["tickers"]),
        "test_start": cfg["data"]["test_start"],
        "test_end": cfg["data"]["test_end"],
        "modelos": json.dumps(cfg["modelos"]),
        "guardrails": json.dumps(cfg.get("guardrails", {})),
        "capital_inicial": cfg["capital"]["inicial"],
    }

    # I-05: validar que los datos nuevos son insertables antes de borrar los viejos.
    # Intentamos el insert del run primero (es la tabla más pequeña).
    # Si falla, no borramos nada.
    try:
        # Paso 1: borrar datos anteriores de este backtest
        sb.table("backtest_trades").delete().eq("backtest_name", name).execute()
        sb.table("backtest_metrics").delete().eq("backtest_name", name).execute()
        sb.table("backtest_runs").delete().eq("name", name).execute()

        # Paso 2: insertar run (si falla aquí, solo perdimos datos del mismo nombre)
        sb.table("backtest_runs").insert(run_row).execute()

        # Paso 3: insertar trades con tracking de fallos (F-04)
        inserted = 0
        failed_batches = 0
        for i in range(0, len(trades_rows), 100):
            batch = trades_rows[i : i + 100]
            try:
                sb.table("backtest_trades").insert(batch).execute()
                inserted += len(batch)
            except Exception as e:
                failed_batches += 1
                log.error(f"  Error batch {i // 100 + 1}: {e} ({len(batch)} trades perdidos)")

        if failed_batches:
            log.warning(
                f"  {failed_batches} batches fallaron. "
                f"{inserted}/{len(trades_rows)} trades guardados."
            )

        # Paso 4: insertar metrics
        sb.table("backtest_metrics").insert(metrics_row).execute()

        log.info(f"Resultados guardados en Supabase: {name}")

    except Exception as e:
        log.error(f"Error fatal guardando backtest '{name}': {e}. Datos pueden estar incompletos.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ML Sandbox Backtester")
    parser.add_argument("--config", required=True, help="Ruta al backtest yaml")
    args = parser.parse_args()

    setup_logging(app_name="backtest")

    cfg = load_backtest_config(args.config)
    name = cfg["backtest"]["name"]

    log.info(f"Iniciando backtest: {name}")
    log.info(f"Periodo: {cfg['data']['test_start']} -> {cfg['data']['test_end']}")
    log.info(f"Tickers: {cfg['data']['tickers']}")

    log.info("Cargando datos silver...")
    df = load_silver(cfg)

    log.info("Cargando modelos...")
    modelos = load_models(cfg["modelos"])
    if not modelos:
        raise ValueError("No se pudieron cargar modelos")

    all_trades: list[dict] = []
    all_stats: dict[str, dict] = {}

    for ticker in cfg["data"]["tickers"]:
        log.info(f"Backtesting {ticker}...")
        trades, stats = run_backtest_ticker(ticker, df, modelos, cfg)
        all_trades.extend(trades)
        all_stats[ticker] = stats

        log.info(f"  P&L: {stats['pnl_total']:+.2f} ({stats['pnl_pct_total']:+.2f}%)")
        log.info(f"  Trades: {stats['n_trades']} | Win rate: {stats['win_rate']}%")
        log.info(f"  Sharpe: {stats['sharpe_ratio']} | Drawdown: {stats['max_drawdown']}%")
        log.info(f"  Guardrails: {stats['guardrail_stats']}")

    # Combinar stats multi-ticker
    if len(all_stats) == 1:
        stats_combined = list(all_stats.values())[0]
    else:
        stats_combined = {
            "capital_inicial": cfg["capital"]["inicial"],
            "capital_final": round(
                sum(s["capital_final"] for s in all_stats.values()), 2
            ),
            "pnl_total": round(sum(s["pnl_total"] for s in all_stats.values()), 2),
            "pnl_pct_total": round(
                sum(s["pnl_pct_total"] for s in all_stats.values()) / len(all_stats), 2
            ),
            "n_trades": sum(s["n_trades"] for s in all_stats.values()),
            "n_wins": sum(s["n_wins"] for s in all_stats.values()),
            "n_losses": sum(s["n_losses"] for s in all_stats.values()),
            "win_rate": round(
                sum(s["win_rate"] for s in all_stats.values()) / len(all_stats), 1
            ),
            "sharpe_ratio": round(
                sum(s["sharpe_ratio"] for s in all_stats.values()) / len(all_stats), 2
            ),
            "max_drawdown": round(
                max(s["max_drawdown"] for s in all_stats.values()), 2
            ),
            "guardrail_stats": {
                k: v
                for s in all_stats.values()
                for k, v in s["guardrail_stats"].items()
            },
        }

    log.info("Guardando resultados...")
    save_results(cfg, all_trades, stats_combined)
    log.info(f"Backtest completado: {name}")


if __name__ == "__main__":
    main()
