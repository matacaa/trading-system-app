"""
apps/api/main.py
────────────────
API REST — conecta frontend Next.js con pipelines Python.
Uso: python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

v3: 16 tickers, candles históricas, selector config live
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Setup ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import sb
from shared.symbols import ALL_SYMBOLS

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

app = FastAPI(title="Trading System API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_live_process: subprocess.Popen | None = None
_live_log_path: Path = ROOT / "data" / "logs" / "pipeline_live.log"

# ── Schemas ───────────────────────────────────────────────────────────────────

class TrainRequest(BaseModel):
    model: str
    ticker: str = "AAPL"
    timeframe: str = "1m"
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    context_tickers: list[str] = []
    columns: list[str] = [
        "ema_9", "ema_12", "ema_21", "rsi_14",
        "macd_line", "macd_signal", "bb_pct", "bb_width",
        "vwap", "atr_14", "returns_5", "volume_norm",
    ]
    params: dict[str, Any] = {}
    experiment_name: str = ""


class BacktestRequest(BaseModel):
    name: str = ""
    tickers: list[str] = ["AAPL"]
    context_tickers: list[str] = []
    test_start: str
    test_end: str
    timeframe: str = "1m"
    modelos: list[dict[str, Any]]
    guardrails: dict[str, Any] = {}
    capital: dict[str, Any] = {}


class LiveConfig(BaseModel):
    config_name: str = "ensemble"


class TradingToggle(BaseModel):
    enabled: bool


class LiveEnsembleConfig(BaseModel):
    tickers: list[str] = ["AAPL"]
    context_tickers: list[str] = []
    modelos: list[dict[str, Any]]
    guardrails: dict[str, Any] = {}
    capital: dict[str, Any] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_pipeline(cmd: list[str], timeout: int = 300) -> dict:
    log.info(f"Ejecutando: {' '.join(cmd)}")
    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        duration = time.time() - start
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout, "stderr": result.stderr,
            "duration": round(duration, 2), "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout después de {timeout}s", "duration": timeout}
    except Exception as e:
        return {"success": False, "error": str(e), "duration": time.time() - start}


def _generate_experiment_yaml(req: TrainRequest) -> tuple[Path, str]:
    ticker_lower = req.ticker.lower()
    exp_name = req.experiment_name.strip() if req.experiment_name.strip() else f"{ticker_lower}_{req.model}_{req.timeframe}_v1"
    config = {
        "experiment": {"name": exp_name, "task": "classification"},
        "model": {"name": req.model, "params": req.params or {}},
        "data": {
            "tickers": [req.ticker], "context_tickers": req.context_tickers,
            "tables": [f"silver_features_{req.timeframe}"], "columns": req.columns,
            "target": "returns", "train_start": req.train_start, "train_end": req.train_end,
            "test_start": req.test_start, "test_end": req.test_end, "dropna": True,
        },
        "output": {"save_model": True, "save_predictions": True, "save_metrics": True},
    }
    tmp = Path(tempfile.mktemp(suffix=".yaml", prefix="train_"))
    with open(tmp, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    return tmp, exp_name


def _generate_backtest_yaml(req: BacktestRequest) -> tuple[Path, str]:
    bt_name = req.name.strip() if req.name.strip() else f"bt_{'_'.join(req.tickers).lower()}_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}"
    g = req.guardrails
    config = {
        "backtest": {"name": bt_name, "description": f"Backtest UI — {req.test_start} a {req.test_end}"},
        "data": {
            "tickers": req.tickers, "context_tickers": req.context_tickers,
            "test_start": req.test_start, "test_end": req.test_end, "timeframe": req.timeframe,
        },
        "modelos": [{"experiment_name": m["experiment_name"], "activo": m.get("activo", True), "peso": m.get("peso", 0.15)} for m in req.modelos],
        "capital": req.capital or {
            "inicial": 100000, "posicion_max_pct": g.get("posicion_max_pct", 10),
            "stop_loss_pct": g.get("stop_loss", 5),
            "take_profit_pct": g.get("take_profit", 10),
            "cierre_fin_dia": g.get("cierre_fin_dia", True),
        },
        "guardrails": {
            "score_threshold": g.get("score_threshold", 50),
            "score_minimo": {"activo": g.get("score_minimo_activo", False), "valor": g.get("score_minimo_valor", 65)},
            "rsi": {"activo": g.get("rsi_activo", False), "compra_max": g.get("rsi_compra_max", 70), "venta_min": g.get("rsi_venta_min", 30)},
            "macd": {"activo": g.get("macd_activo", False)},
            "bollinger": {"activo": g.get("bollinger_activo", False), "compra_max": g.get("bollinger_compra_max", 0.95)},
            "atr_volatilidad": {"activo": g.get("atr_activo", False), "max_atr_pct": g.get("atr_max_pct", 2.0)},
            "volumen": {"activo": g.get("volumen_activo", False), "min_volume_norm": g.get("volumen_min", 0.5)},
            "ema_tendencia": {"activo": g.get("ema_tendencia_activo", False)},
            "vwap_spread": {"activo": g.get("vwap_spread_activo", False), "max_spread_pct": g.get("vwap_max_spread", 2.0)},
            "sentiment": {"activo": g.get("sentiment_activo", False), "min_score": g.get("sentiment_min_score", 0.0)},
            "horario_mercado": {"activo": g.get("horario_mercado_activo", True)},
            "posicion_abierta": {"activo": g.get("posicion_abierta", True)},
            "max_posiciones": {"activo": g.get("max_posiciones_activo", False), "valor": g.get("max_posiciones_valor", 3)},
            "ordenes_diarias_max": {"activo": g.get("ordenes_diarias_activo", False), "valor": g.get("ordenes_diarias_valor", 5)},
            "circuit_breaker": {"activo": g.get("circuit_breaker", False)},
        },
    }
    tmp = Path(tempfile.mktemp(suffix=".yaml", prefix="backtest_"))
    with open(tmp, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    return tmp, bt_name


# ── Endpoints: Health ────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


# ── Endpoints: Data ──────────────────────────────────────────────────────────

@app.get("/api/tickers")
async def list_tickers():
    """Los 16 tickers del universo + flag de si tienen datos."""
    tickers_with_data: set[str] = set()
    for ticker in ALL_SYMBOLS:
        try:
            resp = sb.table("silver_features_1m").select("ticker").eq("ticker", ticker).limit(1).execute()
            if resp.data:
                tickers_with_data.add(ticker)
        except Exception:
            pass

    # Devolver siempre los 16 de ALL_SYMBOLS
    result = []
    for ticker, name in ALL_SYMBOLS.items():
        result.append({
            "ticker": ticker,
            "name": name,
            "has_data": ticker in tickers_with_data,
        })
    return {"tickers": result}


@app.get("/api/data-range")
async def data_range(ticker: str = "AAPL", timeframe: str = "1m"):
    table = f"silver_features_{timeframe}"
    first = sb.table(table).select("ts").eq("ticker", ticker).order("ts").limit(1).execute()
    last = sb.table(table).select("ts").eq("ticker", ticker).order("ts", desc=True).limit(1).execute()
    return {
        "min": first.data[0]["ts"].split("T")[0] if first.data else None,
        "max": last.data[0]["ts"].split("T")[0] if last.data else None,
        "ticker": ticker, "table": table,
    }


@app.get("/api/candles")
async def get_candles(ticker: str = "AAPL", limit: int = 200):
    """Velas RT (datos recientes)."""
    resp = (
        sb.table("raw_ohlcv_rt").select("ts,open,high,low,close,volume")
        .eq("ticker", ticker).order("ts", desc=True).limit(limit).execute()
    )
    return {"candles": list(reversed(resp.data or [])), "ticker": ticker}


@app.get("/api/candles/historical")
async def get_candles_historical(ticker: str = "AAPL", date: str = "", timeframe: str = "1m"):
    """Velas históricas de UN día concreto desde raw_ohlcv o silver_features."""
    if not date:
        return {"candles": [], "ticker": ticker, "error": "Parámetro date requerido"}

    date_start = f"{date}T00:00:00+00:00"
    date_end = f"{date}T23:59:59+00:00"

    # Intentar raw_ohlcv primero
    table = f"raw_ohlcv_{timeframe}"
    try:
        all_rows: list[dict] = []
        offset = 0
        while True:
            resp = (
                sb.table(table).select("ts,open,high,low,close,volume")
                .eq("ticker", ticker).gte("ts", date_start).lte("ts", date_end)
                .order("ts").range(offset, offset + 999).execute()
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

        if all_rows:
            return {"candles": all_rows, "ticker": ticker, "source": table, "count": len(all_rows)}
    except Exception:
        pass

    # Fallback a silver_features
    table = f"silver_features_{timeframe}"
    try:
        all_rows = []
        offset = 0
        while True:
            resp = (
                sb.table(table).select("ts,open,high,low,close,volume")
                .eq("ticker", ticker).gte("ts", date_start).lte("ts", date_end)
                .order("ts").range(offset, offset + 999).execute()
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

        return {"candles": all_rows, "ticker": ticker, "source": table, "count": len(all_rows)}
    except Exception as e:
        return {"candles": [], "ticker": ticker, "error": str(e)}


# ── Endpoints: Models ────────────────────────────────────────────────────────

@app.get("/api/models")
async def list_models(ticker: str = ""):
    """Lista modelos activos, opcionalmente filtrados por ticker."""
    query = (
        sb.table("silver_model_registry")
        .select("experiment_name,model_name,version,is_active,status,metrics_summary,training_duration,created_at,feature_columns,ticker,timeframe")
        .eq("is_active", True).eq("status", "complete")
    )
    if ticker:
        query = query.eq("ticker", ticker)
    resp = query.order("created_at", desc=True).execute()
    return {"models": resp.data or []}


@app.get("/api/models/all")
async def list_all_models():
    resp = (
        sb.table("silver_model_registry")
        .select("experiment_name,model_name,version,is_active,status,metrics_summary,training_duration,created_at,ticker,timeframe")
        .order("created_at", desc=True).limit(50).execute()
    )
    return {"models": resp.data or []}


# ── Endpoints: Train ─────────────────────────────────────────────────────────

@app.post("/api/train")
async def train_model(req: TrainRequest):
    yaml_path, exp_name = _generate_experiment_yaml(req)
    try:
        result = _run_pipeline(
            [sys.executable, "-m", "apps.ml_sandbox.pipeline", "--config", str(yaml_path)],
            timeout=600,
        )
        metrics = None
        if result["success"]:
            resp = (
                sb.table("silver_model_registry")
                .select("experiment_name,version,metrics_summary,training_duration,model_name,ticker,timeframe")
                .eq("experiment_name", exp_name).eq("is_active", True).limit(1).execute()
            )
            if resp.data:
                metrics = resp.data[0]
        return {**result, "experiment_name": exp_name, "metrics": metrics}
    finally:
        yaml_path.unlink(missing_ok=True)


# ── Endpoints: Backtest ──────────────────────────────────────────────────────

@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    yaml_path, bt_name = _generate_backtest_yaml(req)
    try:
        result = _run_pipeline(
            [sys.executable, "-m", "apps.ml_sandbox.backtest", "--config", str(yaml_path)],
            timeout=300,
        )
        bt_result = None
        if result["success"]:
            metrics_resp = sb.table("backtest_metrics").select("*").eq("backtest_name", bt_name).limit(1).execute()
            trades_resp = sb.table("backtest_trades").select("*").eq("backtest_name", bt_name).order("ts_entrada").execute()
            bt_result = {
                "metrics": metrics_resp.data[0] if metrics_resp.data else None,
                "trades": trades_resp.data or [],
            }
        return {**result, "backtest_name": bt_name, "backtest": bt_result}
    finally:
        yaml_path.unlink(missing_ok=True)


@app.get("/api/backtest/results/{name}")
async def get_backtest_results(name: str):
    metrics = sb.table("backtest_metrics").select("*").eq("backtest_name", name).limit(1).execute()
    trades = sb.table("backtest_trades").select("*").eq("backtest_name", name).order("ts_entrada").execute()
    return {
        "metrics": metrics.data[0] if metrics.data else None,
        "trades": trades.data or [],
    }


@app.get("/api/backtest/list")
async def list_backtests():
    """Lista backtests con config completa (para selector en Real-time)."""
    resp = (
        sb.table("backtest_runs")
        .select("name,tickers,test_start,test_end,modelos,guardrails,capital_inicial,created_at")
        .order("created_at", desc=True).limit(20).execute()
    )
    return {"backtests": resp.data or []}


# ── Endpoints: Portfolio ─────────────────────────────────────────────────────

@app.get("/api/portfolio")
async def get_portfolio():
    try:
        from apps.trading_engine.alpaca_trader import get_portfolio_state
        return get_portfolio_state()
    except Exception as e:
        log.error(f"Error portfolio: {e}")
        return {"capital": 0, "posiciones": {}, "n_posiciones": 0, "portfolio_value": 0, "error": str(e)}


# ── Endpoints: Trading Toggle ────────────────────────────────────────────────

@app.get("/api/trading/status")
async def trading_status():
    try:
        resp = sb.table("config").select("trading_enabled,updated_at").eq("id", 1).single().execute()
        return {"trading_enabled": resp.data.get("trading_enabled", False), "updated_at": resp.data.get("updated_at")}
    except Exception as e:
        return {"trading_enabled": False, "error": str(e)}


@app.post("/api/trading/toggle")
async def toggle_trading(body: TradingToggle):
    try:
        sb.table("config").update({
            "trading_enabled": body.enabled,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", 1).execute()
        status = "activado" if body.enabled else "desactivado"
        log.info(f"Trading {status}")
        return {"trading_enabled": body.enabled, "status": status}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


# ── Endpoints: Live Config (selector de ensemble) ───────────────────────────

@app.get("/api/live/config")
async def get_live_config():
    """Lee la configuración activa del ensemble (ensemble.yaml)."""
    ensemble_path = ROOT / "config" / "live" / "ensemble.yaml"
    if not ensemble_path.exists():
        return {"config": None, "error": "ensemble.yaml no encontrado"}
    with open(ensemble_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return {"config": config, "path": str(ensemble_path)}


@app.post("/api/live/config")
async def set_live_config(body: LiveEnsembleConfig):
    """Escribe una nueva configuración de ensemble para el live.
    El usuario debe reiniciar el pipeline para que surta efecto.
    """
    ensemble_path = ROOT / "config" / "live" / "ensemble.yaml"

    config = {
        "data": {
            "tickers": body.tickers,
            "context_tickers": body.context_tickers,
            "timeframe": "1m",
        },
        "modelos": [
            {"experiment_name": m["experiment_name"], "activo": m.get("activo", True), "peso": m.get("peso", 0.15)}
            for m in body.modelos
        ],
        "capital": body.capital or {
            "inicial": 100000, "posicion_max_pct": 10,
            "stop_loss_pct": 5, "take_profit_pct": 10, "cierre_fin_dia": True,
        },
        "guardrails": body.guardrails or {"score_threshold": 50, "posicion_abierta": {"activo": True}},
    }

    with open(ensemble_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)

    pipeline_running = _live_process is not None and _live_process.poll() is None
    log.info(f"Ensemble config actualizada. Pipeline running: {pipeline_running}")

    return {
        "status": "written",
        "restart_needed": pipeline_running,
        "warning": "Reinicia el pipeline para aplicar la nueva configuración" if pipeline_running else None,
    }


# ── Endpoints: Live Engine ───────────────────────────────────────────────────

@app.post("/api/live/start")
async def start_live(config: LiveConfig):
    global _live_process
    if _live_process and _live_process.poll() is None:
        raise HTTPException(400, "El trading engine ya está corriendo")

    # Ensure log dir exists
    _live_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Write stdout/stderr to file instead of PIPE (PIPE blocks on Windows)
    log_file = open(_live_log_path, "w", encoding="utf-8")
    _live_process = subprocess.Popen(
        [sys.executable, "-m", "apps.trading_engine.main"],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    log.info(f"Trading engine arrancado — PID {_live_process.pid}")

    # Quick check: did it crash immediately?
    import asyncio
    await asyncio.sleep(1)
    if _live_process.poll() is not None:
        log_file.close()
        rc = _live_process.returncode
        error_text = ""
        try:
            error_text = _live_log_path.read_text(encoding="utf-8")[-500:]
        except Exception:
            pass
        _live_process = None
        raise HTTPException(500, f"Pipeline crashed on start (exit {rc}): {error_text}")

    return {"status": "started", "pid": _live_process.pid}


@app.post("/api/live/stop")
async def stop_live():
    global _live_process
    if not _live_process or _live_process.poll() is not None:
        _live_process = None
        return {"status": "not_running"}
    _live_process.terminate()
    try:
        _live_process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _live_process.kill()
    pid = _live_process.pid
    _live_process = None
    log.info(f"Trading engine detenido — PID {pid}")
    return {"status": "stopped", "pid": pid}


@app.get("/api/live/status")
async def live_status():
    running = _live_process is not None and _live_process.poll() is None
    # If process died unexpectedly, clean up
    if _live_process is not None and _live_process.poll() is not None:
        log.warning(f"Pipeline process died (exit code {_live_process.poll()})")

    last_log = sb.table("gold_logs").select("run_at,status,duration_s,errores").order("run_at", desc=True).limit(1).execute()
    trading_enabled = False
    try:
        cfg_resp = sb.table("config").select("trading_enabled").eq("id", 1).single().execute()
        trading_enabled = bool(cfg_resp.data.get("trading_enabled", False)) if cfg_resp.data else False
    except Exception:
        pass
    return {
        "running": running,
        "pid": _live_process.pid if running else None,
        "trading_enabled": trading_enabled,
        "last_run": last_log.data[0] if last_log.data else None,
    }


@app.get("/api/live/logs")
async def live_logs(lines: int = 50):
    """Últimas líneas del log del pipeline."""
    if not _live_log_path.exists():
        return {"logs": "", "lines": 0}
    try:
        text = _live_log_path.read_text(encoding="utf-8", errors="replace")
        all_lines = text.strip().split("\n")
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {"logs": "\n".join(tail), "lines": len(tail)}
    except Exception as e:
        return {"logs": f"Error reading log: {e}", "lines": 0}


# ── Endpoints: Signals & Trades ──────────────────────────────────────────────

@app.get("/api/signals/latest")
async def latest_signals(ticker: str = "AAPL"):
    resp = (
        sb.table("gold_signals").select("ts,ticker,experiment_name,y_pred,y_prob,score,run_at")
        .eq("ticker", ticker).order("run_at", desc=True).limit(30)
    ).execute()
    if not resp.data:
        return {"signals": [], "run_at": None}
    latest_run = resp.data[0]["run_at"]
    return {"signals": [s for s in resp.data if s["run_at"] == latest_run], "run_at": latest_run}


@app.get("/api/decisions/today")
async def today_decisions(ticker: str = "AAPL"):
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    resp = (
        sb.table("gold_decisions").select("ts,decision,score_final,ejecutada,motivo_rechazo")
        .eq("ticker", ticker).gte("ts", today).order("ts", desc=True).execute()
    )
    return {"decisions": resp.data or []}


@app.get("/api/trades")
async def get_trades(ticker: str = "AAPL", limit: int = 20):
    resp = (
        sb.table("gold_trades")
        .select("ticker,ts_entrada,precio_entrada,ts_salida,precio_salida,pnl,pnl_pct,status,motivo_salida,qty")
        .eq("ticker", ticker).order("ts_entrada", desc=True).limit(limit).execute()
    )
    return {"trades": resp.data or []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
