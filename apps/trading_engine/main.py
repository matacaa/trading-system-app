"""
main.py — trading_engine
────────────────────────
Pipeline principal: orquesta el flujo completo cada X minutos.

    1. Descarga precios RT desde Alpaca → raw_ohlcv_rt
    2. Descarga noticias RT desde Alpaca → raw_news_rt
    3. Calcula sentiment con FinBERT
    4. Calcula indicadores técnicos → silver_features_rt
    5. Carga modelos desde silver_model_registry
    6. Genera predicciones por ticker (shared.inference)
    7. Evalúa guardarraíles y decide (shared.guardrails)
    8. Ejecuta órdenes en Alpaca paper
    9. Guarda señales, decisiones, timings y logs en PostgreSQL

Uso:
    python -m apps.trading_engine.main
    python -m apps.trading_engine.main --once
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

from apps.trading_engine.alpaca_trader import execute_order, get_orders_today, get_portfolio_state
from apps.trading_engine.db import save_decision, save_log, save_signals, save_timing
from apps.trading_engine.reconciliation import reconcile_trades
from shared.config import cfg as app_cfg
from shared.guardrails import decide
from shared.inference import load_models, predict_ensemble
from shared.utils.logging import setup_logging

log = logging.getLogger(__name__)


def _is_trading_enabled() -> bool:
    """Lee config.trading_enabled de PostgreSQL.
    Controla si las órdenes se ejecutan (botón 'Invertir' del frontend).
    Si la tabla no existe o hay error, retorna False (fail-safe).
    """
    try:
        from shared.db import query_one
        row = query_one("SELECT trading_enabled FROM config WHERE id = 1")
        return bool(row.get("trading_enabled", False)) if row else False
    except Exception as e:
        log.warning(f"No se pudo leer config.trading_enabled: {e}. Asumiendo False (no operar).")
        return False


def load_config() -> dict:
    """Carga configuración mergeando trading.yaml con el ensemble yaml."""
    trading_yaml = app_cfg.config_dir / "live" / "trading.yaml"
    if not trading_yaml.exists():
        raise FileNotFoundError(
            f"No se encontró {trading_yaml}. "
            f"Crea el fichero a partir de config/live/trading.yaml.example"
        )

    with open(trading_yaml, encoding="utf-8") as f:
        trading_cfg = yaml.safe_load(f)

    # Cargar el yaml del ensemble activo
    ensemble_ref = trading_cfg.get(
        "active_ensemble_config", "config/live/ensemble.yaml"
    )
    ensemble_path = app_cfg.repo_root / ensemble_ref
    if not ensemble_path.exists():
        raise FileNotFoundError(
            f"No se encontró ensemble config: {ensemble_path}. "
            f"Verifica active_ensemble_config en {trading_yaml}"
        )

    # A-05: validar que no apunta a un backtest yaml
    if "backtest" in str(ensemble_ref).lower():
        log.warning(
            f"active_ensemble_config apunta a un backtest ({ensemble_ref}). "
            f"El live debería usar config/live/ensemble.yaml"
        )

    with open(ensemble_path, encoding="utf-8") as f:
        ensemble_cfg = yaml.safe_load(f)

    cfg = {**ensemble_cfg}
    cfg["pipeline"] = trading_cfg.get("pipeline", {})

    return cfg


def run(cfg: dict, modelos: list) -> None:
    """Ejecuta una iteración completa del pipeline."""
    from apps.ingestion_live.alpaca_news import fetch_news
    from apps.ingestion_live.alpaca_prices import fetch_prices
    from apps.ingestion_live.finbert_rt import get_sentiment
    from apps.ingestion_live.silver_rt import compute_silver_rt

    start = datetime.now(UTC)
    run_id = start.strftime("%Y%m%d_%H%M%S")
    tickers = cfg.get("data", {}).get("tickers", [])
    context_tickers = cfg.get("data", {}).get("context_tickers", [])
    all_tickers = list(dict.fromkeys(tickers + context_tickers))  # deduplicated
    timeframe = cfg["pipeline"].get("timeframe", "1m")
    cfg_gr = cfg.get("guardrails", {})
    cfg_capital = cfg.get("capital", {})
    errores: list[str] = []
    senales = 0
    ordenes = 0

    log.info(f"{'='*60}")
    log.info(f"Iniciando pipeline — run_id: {run_id}")
    log.info(f"Tickers: {tickers} | Context: {context_tickers} | Timeframe: {timeframe}")

    try:
        # 1. Descargar precios RT (incluye context_tickers)
        log.info("-- Descargando precios RT...")
        t0 = time.time()
        fetch_prices(tickers=all_tickers, timeframe=timeframe, bars=100)
        save_timing("fetch_prices", time.time() - t0, run_id=run_id)

        # 2. Descargar noticias RT
        log.info("-- Descargando noticias RT...")
        t0 = time.time()
        fetch_news(tickers=all_tickers, hours=24)
        save_timing("fetch_news", time.time() - t0, run_id=run_id)

        # 3. Calcular sentiment
        log.info("-- Calculando sentiment...")
        t0 = time.time()
        sentiment = get_sentiment(tickers=all_tickers, hours=24)
        save_timing("sentiment", time.time() - t0, run_id=run_id)

        # 4. Calcular indicadores silver RT (incluye context_tickers)
        log.info("-- Calculando indicadores silver RT...")
        t0 = time.time()
        df_silver = compute_silver_rt(tickers=all_tickers, timeframe=timeframe)
        save_timing("silver_rt", time.time() - t0, run_id=run_id)

        if df_silver.empty:
            log.warning("DataFrame silver vacío — abortando iteración")
            save_log(
                duration_s=( datetime.now(UTC) - start).total_seconds(),
                tickers_procesados=tickers,
                senales_generadas=0,
                ordenes_ejecutadas=0,
                errores=["silver_features_rt vacío"],
                status="error",
                run_id=run_id,
            )
            return

        # Obtener estado del portfolio
        log.info("-- Obteniendo estado del portfolio...")
        t0 = time.time()
        portfolio = get_portfolio_state()
        ordenes_hoy = get_orders_today()
        save_timing("portfolio_state", time.time() - t0, run_id=run_id)

        # F-34: si el portfolio state falló, no operar
        if portfolio.get("error"):
            log.error("Portfolio state falló — abortando iteración (no se operará)")
            save_log(
                duration_s=(datetime.now(UTC) - start).total_seconds(),
                tickers_procesados=tickers,
                senales_generadas=0,
                ordenes_ejecutadas=0,
                errores=["portfolio_state_error"],
                status="error",
                run_id=run_id,
            )
            return

        # Procesar cada ticker
        for ticker in tickers:
            log.info(f"-- Procesando {ticker}...")

            try:
                df_ticker = df_silver[df_silver["ticker"] == ticker].copy()
                if df_ticker.empty:
                    log.warning(f"  {ticker}: sin datos silver")
                    continue

                # Enriquecer con features de context_tickers
                if context_tickers:
                    feature_cols_to_merge = [
                        "ema_9", "ema_12", "ema_21", "rsi_14",
                        "macd_line", "macd_signal", "bb_pct", "bb_width",
                        "vwap", "atr_14", "returns_5", "volume_norm",
                    ]
                    for ctx_ticker in context_tickers:
                        if ctx_ticker == ticker:
                            continue
                        ctx_df = df_silver[df_silver["ticker"] == ctx_ticker].copy()
                        if ctx_df.empty:
                            continue
                        rename_map = {c: f"{ctx_ticker}_{c}" for c in feature_cols_to_merge if c in ctx_df.columns}
                        ctx_df = ctx_df[["ts"] + list(rename_map.keys())].rename(columns=rename_map)
                        df_ticker = df_ticker.merge(ctx_df, on="ts", how="left")
                    # Rellenar NaN de context con 0
                    ctx_cols = [c for c in df_ticker.columns if any(c.startswith(f"{t}_") for t in context_tickers)]
                    if ctx_cols:
                        df_ticker[ctx_cols] = df_ticker[ctx_cols].fillna(0)

                # Predicción con el ensemble
                t0 = time.time()
                row = df_ticker.iloc[-1]
                score, detalle, signals = predict_ensemble(
                    row, modelos, df_hist=df_ticker
                )
                save_timing("predict", time.time() - t0, run_id=run_id, ticker=ticker)

                senales += len(signals)
                save_signals(signals)

                # Estado para guardarraíles
                estado = {
                    "posicion_abierta": ticker in portfolio.get("posiciones", {}),
                    "n_posiciones": portfolio.get("n_posiciones", 0),
                    "ordenes_hoy": ordenes_hoy,
                }

                # Decisión
                t0 = time.time()
                decision = decide(ticker, score, row, cfg_gr, estado)
                save_timing("decide", time.time() - t0, run_id=run_id, ticker=ticker)
                save_decision(decision, detalle)

                # Ejecutar orden si procede
                if decision["decision"] == "BUY":
                    # Verificar si trading está habilitado (botón invertir del frontend)
                    trading_enabled = _is_trading_enabled()
                    if not trading_enabled:
                        log.info(
                            f"  {ticker}: BUY con score {score:.1f} pero trading desactivado "
                            f"(config.trading_enabled=false). Señal registrada, orden NO enviada."
                        )
                        decision["ejecutada"] = False
                        decision["motivo_rechazo"] = "trading_desactivado"
                        save_decision(decision, detalle)
                    else:
                        t0 = time.time()
                        trade = execute_order(ticker, decision, cfg_capital, portfolio)
                        save_timing(
                            "execute_order", time.time() - t0, run_id=run_id, ticker=ticker
                        )

                        if trade:
                            ordenes += 1
                            ordenes_hoy += 1
                            decision["ejecutada"] = True
                            save_decision(decision, detalle)

            except Exception as e:
                msg = f"Error procesando {ticker}: {e}"
                log.error(msg)
                errores.append(msg)

    except Exception as e:
        msg = f"Error crítico en pipeline: {e}"
        log.error(msg)
        errores.append(msg)

    # Guardar log global
    duration = (datetime.now(UTC) - start).total_seconds()
    save_log(
        duration_s=duration,
        tickers_procesados=tickers,
        senales_generadas=senales,
        ordenes_ejecutadas=ordenes,
        errores=errores,
        status="ok" if not errores else "error",
        run_id=run_id,
    )

    log.info(
        f"Pipeline completado en {duration:.1f}s — "
        f"señales: {senales} | órdenes: {ordenes}"
    )

    # Reconciliar trades abiertos con Alpaca (F-39)
    try:
        n_reconciled = reconcile_trades()
        if n_reconciled:
            log.info(f"Reconciliation: {n_reconciled} trades actualizados")
    except Exception as e:
        log.warning(f"Error en reconciliation: {e}")


def main():
    parser = argparse.ArgumentParser(description="Trading Engine Pipeline")
    parser.add_argument("--once", action="store_true", help="Ejecutar una sola vez")
    args = parser.parse_args()

    setup_logging(
        app_name="trading-engine",
        log_file=app_cfg.logs_dir / "trading_engine.log",
    )

    log.info("Cargando configuración...")
    cfg = load_config()

    interval = cfg["pipeline"].get("interval_minutes", 1)
    log.info(f"Intervalo: {interval} minutos")

    log.info("Cargando modelos...")
    modelos = load_models(cfg["modelos"])
    if not modelos:
        log.error("No se pudieron cargar modelos — abortando")
        sys.exit(1)
    log.info(f"{len(modelos)} modelos cargados")

    if args.once:
        run(cfg, modelos)
        return

    log.info(f"Iniciando scheduler — cada {interval} minuto(s)")
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run,
        trigger="interval",
        minutes=interval,
        args=[cfg, modelos],
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Pipeline detenido por el usuario")


if __name__ == "__main__":
    main()
