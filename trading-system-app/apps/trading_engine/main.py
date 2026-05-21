"""
main.py — trading_engine
────────────────────────
Pipeline principal multi-usuario — Fase 6.11.

Flujo de 4 pasos por ticker:
    1. Guardrails PRE por usuario (datos de mercado, sin score ML)
    2. Inferencia sistema (1x por ticker, compartida) + señales rule-based
    3. Inferencia custom por usuario (solo si pasa PRE y tiene modelos)
    4. Guardrail POST (score_minimo) → LONG/SHORT según ticker_direction

Cambios respecto al pipeline anterior:
    - Multi-usuario: cada usuario tiene sus propios guardrails y modelos
    - LONG/SHORT en vez de BUY/SELL
    - 25 señales rule-based integradas al score
    - Modelos custom por usuario (descarga de Blob Storage)
    - No ejecuta órdenes (app de alertas, no de ejecución)

Uso:
    python -m apps.trading_engine.main
    python -m apps.trading_engine.main --once
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

from apps.trading_engine.db import save_decision, save_log, save_signals, save_timing
from apps.trading_engine.reconciliation import reconcile_trades
from shared.config import cfg as app_cfg
from shared.guardrails import check_guardrails_post, check_guardrails_pre
from shared.inference import (
    compute_user_score,
    load_models,
    predict_ensemble,
    run_custom_models,
)
from shared.signals.evaluator import combine_scores, evaluate_signals
from shared.squawk_generator import generate_squawk_for_user
from shared.utils.logging import setup_logging

log = logging.getLogger(__name__)

# Guardrails por defecto del sistema
DEFAULT_GUARDRAILS = {
    "score_threshold": 50,
    "horario_mercado": {"activo": True},
    "posicion_abierta": {"activo": True},
}


def _is_trading_enabled() -> bool:
    """Lee config.trading_enabled de PostgreSQL."""
    try:
        from shared.db import query_one
        row = query_one("SELECT trading_enabled FROM config WHERE id = 1")
        return bool(row.get("trading_enabled", False)) if row else False
    except Exception as e:
        log.warning(f"No se pudo leer config.trading_enabled: {e}. Asumiendo False.")
        return False


def _get_users_for_ticker(ticker: str) -> list[dict]:
    """Busca usuarios activos que siguen este ticker con sus preferencias."""
    from shared.db import query

    rows = query(
        """SELECT u.id, u.locale, up.guardrail_overrides,
                  up.models_config, up.ticker_direction
           FROM users u
           JOIN user_preferences up ON up.user_id = u.id
           WHERE u.is_active = true
             AND up.tickers @> %s::jsonb""",
        [json.dumps([ticker])],
    )
    return rows


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

    ensemble_ref = trading_cfg.get(
        "active_ensemble_config", "config/live/ensemble.yaml"
    )
    ensemble_path = app_cfg.repo_root / ensemble_ref
    if not ensemble_path.exists():
        raise FileNotFoundError(
            f"No se encontró ensemble config: {ensemble_path}. "
            f"Verifica active_ensemble_config en {trading_yaml}"
        )

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
    """Ejecuta una iteración completa del pipeline multi-usuario."""
    from apps.ingestion_live.alpaca_news import fetch_news
    from apps.ingestion_live.alpaca_prices import fetch_prices
    from apps.ingestion_live.finbert_rt import get_sentiment
    from apps.ingestion_live.silver_rt import compute_silver_rt

    start = datetime.now(UTC)
    run_id = start.strftime("%Y%m%d_%H%M%S")
    tickers = cfg.get("data", {}).get("tickers", [])
    context_tickers = cfg.get("data", {}).get("context_tickers", [])
    all_tickers = list(dict.fromkeys(tickers + context_tickers))
    timeframe = cfg["pipeline"].get("timeframe", "1m")
    cfg_signals = cfg.get("signals", {})
    signal_weight = cfg.get("signal_weight", 0.2)
    errores: list[str] = []
    senales = 0
    squawks_total = 0

    log.info(f"{'='*60}")
    log.info(f"Pipeline multi-usuario — run_id: {run_id}")
    log.info(f"Tickers: {tickers} | Context: {context_tickers} | TF: {timeframe}")

    try:
        # ── Ingestion compartida ──────────────────────────────────────
        log.info("-- Descargando precios RT...")
        t0 = time.time()
        fetch_prices(tickers=all_tickers, timeframe=timeframe, bars=100)
        save_timing("fetch_prices", time.time() - t0, run_id=run_id)

        log.info("-- Descargando noticias RT...")
        t0 = time.time()
        fetch_news(tickers=all_tickers, hours=24)
        save_timing("fetch_news", time.time() - t0, run_id=run_id)

        log.info("-- Calculando sentiment...")
        t0 = time.time()
        get_sentiment(tickers=all_tickers, hours=24)
        save_timing("sentiment", time.time() - t0, run_id=run_id)

        log.info("-- Calculando indicadores silver RT...")
        t0 = time.time()
        df_silver = compute_silver_rt(tickers=all_tickers, timeframe=timeframe)
        save_timing("silver_rt", time.time() - t0, run_id=run_id)

        if df_silver.empty:
            log.warning("DataFrame silver vacío — abortando iteración")
            save_log(
                duration_s=(datetime.now(UTC) - start).total_seconds(),
                tickers_procesados=tickers,
                senales_generadas=0,
                ordenes_ejecutadas=0,
                errores=["silver_features_rt vacío"],
                status="error",
                run_id=run_id,
            )
            return

        # ── Procesar cada ticker ──────────────────────────────────────
        for ticker in tickers:
            log.info(f"-- Procesando {ticker}...")

            try:
                df_ticker = df_silver[df_silver["ticker"] == ticker].copy()
                if df_ticker.empty:
                    log.warning(f"  {ticker}: sin datos silver")
                    continue

                # Enriquecer con features de context_tickers
                if context_tickers:
                    df_ticker = _enrich_context(df_ticker, df_silver, context_tickers, ticker)

                row = df_ticker.iloc[-1]

                # ── PASO 2: Inferencia sistema (compartida, 1x por ticker) ──
                t0 = time.time()
                score_sistema, detalle, signals_ml = predict_ensemble(
                    row, modelos, df_hist=df_ticker
                )
                save_timing("predict_system", time.time() - t0, run_id=run_id, ticker=ticker)

                senales += len(signals_ml)
                save_signals(signals_ml)

                # ── PASO 2b: Señales rule-based (compartidas, 1x por ticker) ──
                t0 = time.time()
                active_signals = cfg_signals.get("active", None)
                triggered_signals, score_signals, signal_texts = evaluate_signals(
                    row, df_hist=df_ticker, active_signals=active_signals,
                    signal_config=cfg_signals.get("config", {}),
                )
                save_timing("signals", time.time() - t0, run_id=run_id, ticker=ticker)

                # Combinar score ML + señales para obtener score base
                score_base = combine_scores(score_sistema, score_signals, signal_weight)

                log.info(
                    f"  {ticker}: score_sistema={score_sistema:.1f} "
                    f"score_signals={score_signals:.1f} score_base={score_base:.1f} "
                    f"signals_triggered={len(triggered_signals)}"
                )

                # ── PER USER: Pasos 1, 3, 4 ──────────────────────────────
                users = _get_users_for_ticker(ticker)
                if not users:
                    log.debug(f"  {ticker}: ningún usuario sigue este ticker")
                    continue

                for user in users:
                    user_id = str(user["id"])
                    user_locale = user.get("locale", "es")
                    user_guardrails = user.get("guardrail_overrides") or {}
                    user_models_config = user.get("models_config") or {}
                    user_ticker_direction = (user.get("ticker_direction") or {}).get(
                        ticker, "long"
                    )

                    # Merge guardrails: defaults + user overrides (por ticker o globales)
                    ticker_gr = user_guardrails.get(ticker, user_guardrails)
                    merged_gr = {**DEFAULT_GUARDRAILS, **ticker_gr}

                    # PASO 1: Guardrails PRE (datos de mercado, sin score)
                    estado_user = {
                        "posicion_abierta": False,
                        "n_posiciones": 0,
                        "ordenes_hoy": 0,
                    }
                    passes_pre, motivo_pre = check_guardrails_pre(
                        row, merged_gr, estado_user
                    )

                    if not passes_pre:
                        log.info(f"  {ticker} user={user_id}: PRE rechazado — {motivo_pre}")
                        generate_squawk_for_user(
                            user_id=user_id,
                            ticker=ticker,
                            squawk_type="HOLD",
                            score=0.0,
                            row=row,
                            detalle=detalle,
                            signal_texts=signal_texts,
                            motivo_rechazo=motivo_pre,
                            guardrails_config=merged_gr,
                            run_id=run_id,
                            decision_ts=str(row.get("ts", "")),
                            locale=user_locale,
                            ticker_direction=user_ticker_direction,
                        )
                        squawks_total += 1
                        continue

                    # PASO 3: Inferencia custom (si tiene modelos propios)
                    score_custom = None
                    if user_models_config.get("custom_models"):
                        try:
                            t0 = time.time()
                            score_custom = run_custom_models(
                                user_id=user_id,
                                ticker=ticker,
                                models_config=user_models_config,
                                row=row,
                                df_hist=df_ticker,
                            )
                            save_timing(
                                "predict_custom", time.time() - t0,
                                run_id=run_id, ticker=ticker,
                            )
                        except Exception as e:
                            log.warning(f"  Custom models error user={user_id}: {e}")

                    # Combinar score sistema + custom
                    score_final = compute_user_score(
                        score_base, score_custom, user_models_config
                    )

                    # PASO 4: Guardrail POST (score_minimo)
                    passes_post, motivo_post = check_guardrails_post(
                        score_final, merged_gr
                    )

                    if not passes_post:
                        log.info(
                            f"  {ticker} user={user_id}: POST rechazado — "
                            f"{motivo_post} (score={score_final:.1f})"
                        )
                        generate_squawk_for_user(
                            user_id=user_id,
                            ticker=ticker,
                            squawk_type="HOLD",
                            score=score_final,
                            row=row,
                            detalle=detalle,
                            signal_texts=signal_texts,
                            motivo_rechazo=motivo_post,
                            guardrails_config=merged_gr,
                            run_id=run_id,
                            decision_ts=str(row.get("ts", "")),
                            locale=user_locale,
                            ticker_direction=user_ticker_direction,
                        )
                        squawks_total += 1
                        continue

                    # ¡Pasa todos los guardrails! → LONG o SHORT
                    squawk_type = "LONG" if user_ticker_direction == "long" else "SHORT"

                    log.info(
                        f"  {ticker} user={user_id}: {squawk_type} — "
                        f"score={score_final:.1f}"
                    )

                    # Guardar decisión
                    decision = {
                        "ts": str(row.get("ts", datetime.now(UTC).isoformat())),
                        "ticker": ticker,
                        "decision": squawk_type,
                        "score_final": round(score_final, 2),
                        "ejecutada": False,
                        "motivo_rechazo": "",
                    }
                    save_decision(decision, detalle)

                    # Generar squawk con audio
                    generate_squawk_for_user(
                        user_id=user_id,
                        ticker=ticker,
                        squawk_type=squawk_type,
                        score=score_final,
                        row=row,
                        detalle=detalle,
                        signal_texts=signal_texts,
                        motivo_rechazo="",
                        guardrails_config=merged_gr,
                        run_id=run_id,
                        decision_ts=str(row.get("ts", "")),
                        locale=user_locale,
                        ticker_direction=user_ticker_direction,
                    )
                    squawks_total += 1

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
        ordenes_ejecutadas=squawks_total,
        errores=errores,
        status="ok" if not errores else "error",
        run_id=run_id,
    )

    log.info(
        f"Pipeline completado en {duration:.1f}s — "
        f"señales: {senales} | squawks: {squawks_total}"
    )

    # Reconciliar trades abiertos con Alpaca (F-39)
    try:
        n_reconciled = reconcile_trades()
        if n_reconciled:
            log.info(f"Reconciliation: {n_reconciled} trades actualizados")
    except Exception as e:
        log.warning(f"Error en reconciliation: {e}")


def _enrich_context(
    df_ticker, df_silver, context_tickers: list[str], ticker: str,
):
    """Enriquece df_ticker con features de context_tickers."""
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
        rename_map = {
            c: f"{ctx_ticker}_{c}"
            for c in feature_cols_to_merge
            if c in ctx_df.columns
        }
        ctx_df = ctx_df[["ts"] + list(rename_map.keys())].rename(columns=rename_map)
        df_ticker = df_ticker.merge(ctx_df, on="ts", how="left")

    ctx_cols = [
        c for c in df_ticker.columns
        if any(c.startswith(f"{t}_") for t in context_tickers)
    ]
    if ctx_cols:
        df_ticker[ctx_cols] = df_ticker[ctx_cols].fillna(0)

    return df_ticker


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

    log.info("Cargando modelos del sistema...")
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
