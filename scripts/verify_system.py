"""
verify_system.py
────────────────
Script de verificación pre-arranque.
Ejecutar DESPUÉS de:
  1. Ejecutar schema_fixes.sql en Supabase
  2. pip install -e .

Uso:
    cd C:\\Users\\jgrma\\Desktop\\APIs\\trading-system
    .venv\\Scripts\\activate
    python scripts/verify_system.py

Cada paso reporta ✅ o ❌ con detalle del error.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results: list[tuple[str, str, str]] = []


def check(name: str, fn):
    """Ejecuta una verificación y registra resultado."""
    try:
        msg = fn()
        results.append((PASS, name, msg or "OK"))
    except Exception as e:
        results.append((FAIL, name, str(e)))


def warn_check(name: str, fn):
    """Verificación no bloqueante (warning)."""
    try:
        msg = fn()
        results.append((PASS, name, msg or "OK"))
    except Exception as e:
        results.append((WARN, name, str(e)))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ENTORNO Y DEPENDENCIAS
# ═══════════════════════════════════════════════════════════════════════════════

def check_python_version():
    v = sys.version_info
    assert v.major == 3 and v.minor >= 11, f"Requiere Python 3.11+, tienes {v.major}.{v.minor}"
    return f"Python {v.major}.{v.minor}.{v.micro}"

def check_import_core():
    import pandas, numpy, yaml, dotenv, supabase, pydantic
    return f"pandas={pandas.__version__}, numpy={numpy.__version__}"

def check_import_apscheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    return "APScheduler importa correctamente"

def check_import_alpaca():
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient
    return "alpaca-py importa correctamente"

def check_import_ml():
    import torch, xgboost, lightgbm, sklearn
    return f"torch={torch.__version__}, xgboost={xgboost.__version__}"

def check_import_transformers():
    import transformers
    return f"transformers={transformers.__version__}"

def check_import_exchange_calendars():
    import exchange_calendars
    return "exchange_calendars OK"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def check_config():
    from shared.config import cfg
    assert cfg.supabase_url, "SUPABASE_URL vacía"
    assert cfg.supabase_key, "SUPABASE_KEY vacía"
    assert cfg.alpaca_api_key, "ALPACA_API_KEY vacía"
    assert cfg.alpaca_paper, "ALPACA_BASE_URL no apunta a paper!"
    return f"Supabase: {cfg.supabase_url[:30]}... | Alpaca paper: {cfg.alpaca_paper}"

def check_paths():
    from shared.config import cfg
    assert cfg.models_dir.exists(), f"models_dir no existe: {cfg.models_dir}"
    assert cfg.config_dir.exists(), f"config_dir no existe: {cfg.config_dir}"
    models = list(cfg.models_dir.glob("*.pkl")) + list(cfg.models_dir.glob("*.pt"))
    return f"models_dir: {len(models)} modelos encontrados"

def check_yaml_configs():
    from shared.config import cfg
    import yaml
    trading_yaml = cfg.config_dir / "live" / "trading.yaml"
    ensemble_yaml = cfg.config_dir / "live" / "ensemble.yaml"
    assert trading_yaml.exists(), f"No existe: {trading_yaml}"
    assert ensemble_yaml.exists(), f"No existe: {ensemble_yaml}"
    with open(ensemble_yaml) as f:
        ens = yaml.safe_load(f)
    n_modelos = len(ens.get("modelos", []))
    tickers = ens.get("data", {}).get("tickers", [])
    score_threshold = ens.get("guardrails", {}).get("score_threshold", 50)
    return f"ensemble: {n_modelos} modelos, tickers={tickers}, score_threshold={score_threshold}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SUPABASE — CONECTIVIDAD Y SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

def check_supabase_connection():
    from shared.db import sb
    resp = sb.table("symbols").select("ticker").limit(3).execute()
    tickers = [r["ticker"] for r in resp.data]
    return f"Conectado. Symbols: {tickers}"

def check_table_config():
    from shared.db import sb
    resp = sb.table("config").select("trading_enabled").eq("id", 1).single().execute()
    enabled = resp.data.get("trading_enabled")
    return f"config.trading_enabled = {enabled} (circuit breaker {'OFF' if enabled else 'ON'})"

def check_table_gold_logs_run_id():
    from shared.db import sb
    resp = sb.table("gold_logs").select("run_id").limit(1).execute()
    return "gold_logs.run_id existe"

def check_table_silver_features_columns():
    from shared.db import sb
    resp = sb.table("silver_features_1m").select("sentiment_label_encoded,news_count_1h").limit(1).execute()
    return "silver_features_1m tiene sentiment_label_encoded y news_count_1h"

def check_table_silver_rt_columns():
    from shared.db import sb
    resp = sb.table("silver_features_rt").select("news_count_1h,news_count_24h,has_news").limit(1).execute()
    return "silver_features_rt tiene news_count_1h, news_count_24h, has_news"

def check_table_ingestion_log():
    """Verifica nombre correcto de tabla ingestion_log."""
    from shared.db import sb
    try:
        sb.table("ingestion_log").select("ticker").limit(1).execute()
        return "tabla 'ingestion_log' (singular) existe"
    except Exception:
        try:
            sb.table("ingestion_logs").select("ticker").limit(1).execute()
            raise AssertionError(
                "La tabla se llama 'ingestion_logs' (plural) pero el código usa 'ingestion_log' (singular). "
                "Ejecuta: ALTER TABLE ingestion_logs RENAME TO ingestion_log;"
            )
        except AssertionError:
            raise
        except Exception:
            raise AssertionError(
                "Ni 'ingestion_log' ni 'ingestion_logs' existen. "
                "Si nunca ejecutaste el pipeline histórico, esto es normal."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MODELOS — REGISTRY Y CARGA
# ═══════════════════════════════════════════════════════════════════════════════

def check_model_registry():
    from shared.db import sb
    resp = (
        sb.table("silver_model_registry")
        .select("experiment_name,version,is_active,status,file_path")
        .eq("is_active", True)
        .eq("status", "complete")
        .execute()
    )
    activos = resp.data or []
    if not activos:
        raise AssertionError("No hay modelos activos con status='complete' en silver_model_registry")
    nombres = [m["experiment_name"] for m in activos]
    return f"{len(activos)} modelos activos: {nombres}"

def check_model_files():
    from shared.config import cfg
    from shared.db import sb
    resp = (
        sb.table("silver_model_registry")
        .select("experiment_name,file_path")
        .eq("is_active", True)
        .eq("status", "complete")
        .execute()
    )
    missing = []
    found = []
    for m in resp.data or []:
        fp = m.get("file_path", "")
        if not fp:
            missing.append(f"{m['experiment_name']} (sin file_path)")
            continue
        # Buscar en models_dir (A-02: solo filename)
        from pathlib import Path
        full = Path(fp)
        alt = cfg.models_dir / full.name
        if full.exists():
            found.append(m["experiment_name"])
        elif alt.exists():
            found.append(f"{m['experiment_name']} (via models_dir)")
        else:
            missing.append(f"{m['experiment_name']} → {fp}")

    if missing:
        raise AssertionError(f"Modelos no encontrados en disco: {missing}")
    return f"{len(found)} modelos encontrados en disco"

def check_model_load():
    """Intenta cargar los modelos del ensemble (sin predecir)."""
    import yaml
    from shared.config import cfg
    from shared.inference import load_models
    ensemble_yaml = cfg.config_dir / "live" / "ensemble.yaml"
    with open(ensemble_yaml) as f:
        ens = yaml.safe_load(f)
    modelos = load_models(ens["modelos"])
    if not modelos:
        raise AssertionError("load_models devolvió 0 modelos. Revisa registry y ficheros.")
    nombres = [m["experiment_name"] for m in modelos]
    return f"{len(modelos)} modelos cargados OK: {nombres}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ALPACA — CONECTIVIDAD
# ═══════════════════════════════════════════════════════════════════════════════

def check_alpaca_account():
    from apps.trading_engine.alpaca_trader import _get_trading_client
    client = _get_trading_client()
    account = client.get_account()
    return (
        f"Cuenta Alpaca OK. Cash: ${float(account.cash):,.2f} | "
        f"Portfolio: ${float(account.portfolio_value):,.2f}"
    )

def check_alpaca_positions():
    from apps.trading_engine.alpaca_trader import get_portfolio_state
    state = get_portfolio_state()
    if state.get("error"):
        raise AssertionError("Error obteniendo portfolio state")
    return f"Posiciones abiertas: {state['n_posiciones']} | Capital: ${state['capital']:,.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DATOS RECIENTES
# ═══════════════════════════════════════════════════════════════════════════════

def check_recent_ohlcv_rt():
    from shared.db import sb
    resp = (
        sb.table("raw_ohlcv_rt")
        .select("ts,ticker")
        .order("ts", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise AssertionError("raw_ohlcv_rt vacía — no hay datos RT previos")
    last = resp.data[0]
    return f"Última barra RT: {last['ticker']} @ {last['ts']}"

def check_recent_silver_rt():
    from shared.db import sb
    resp = (
        sb.table("silver_features_rt")
        .select("ts,ticker")
        .order("ts", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise AssertionError("silver_features_rt vacía — no hay features RT previos")
    last = resp.data[0]
    return f"Última feature RT: {last['ticker']} @ {last['ts']}"

def check_recent_signals():
    from shared.db import sb
    resp = (
        sb.table("gold_signals")
        .select("ts,ticker,experiment_name")
        .order("ts", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return "Sin señales previas (normal si es primera ejecución)"
    last = resp.data[0]
    return f"Última señal: {last['ticker']} {last['experiment_name']} @ {last['ts']}"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  VERIFICACIÓN PRE-ARRANQUE — trading-system")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)
    print()

    # 1. Entorno
    print("── 1. Entorno y dependencias ──")
    check("Python version", check_python_version)
    check("Imports core (pandas, numpy, yaml, supabase)", check_import_core)
    check("APScheduler", check_import_apscheduler)
    check("alpaca-py", check_import_alpaca)
    check("ML (torch, xgboost, lightgbm)", check_import_ml)
    warn_check("transformers (FinBERT)", check_import_transformers)
    check("exchange_calendars", check_import_exchange_calendars)
    print()

    # 2. Configuración
    print("── 2. Configuración ──")
    check("shared.config.cfg", check_config)
    check("Paths (models_dir, config_dir)", check_paths)
    check("YAMLs (trading.yaml, ensemble.yaml)", check_yaml_configs)
    print()

    # 3. Supabase
    print("── 3. Supabase ──")
    check("Conexión Supabase", check_supabase_connection)
    check("Tabla config (circuit breaker)", check_table_config)
    check("gold_logs.run_id", check_table_gold_logs_run_id)
    check("silver_features_1m columnas nuevas", check_table_silver_features_columns)
    check("silver_features_rt columnas nuevas", check_table_silver_rt_columns)
    warn_check("Tabla ingestion_log", check_table_ingestion_log)
    print()

    # 4. Modelos
    print("── 4. Modelos ──")
    check("Model registry (modelos activos)", check_model_registry)
    check("Ficheros de modelo en disco", check_model_files)
    check("Carga de modelos (load_models)", check_model_load)
    print()

    # 5. Alpaca
    print("── 5. Alpaca ──")
    check("Cuenta Alpaca", check_alpaca_account)
    check("Portfolio state", check_alpaca_positions)
    print()

    # 6. Datos
    print("── 6. Datos recientes ──")
    warn_check("Última barra raw_ohlcv_rt", check_recent_ohlcv_rt)
    warn_check("Última feature silver_features_rt", check_recent_silver_rt)
    warn_check("Última señal gold_signals", check_recent_signals)
    print()

    # Resumen
    print("=" * 70)
    n_pass = sum(1 for s, _, _ in results if s == PASS)
    n_fail = sum(1 for s, _, _ in results if s == FAIL)
    n_warn = sum(1 for s, _, _ in results if s == WARN)
    print(f"  RESULTADO: {n_pass} OK | {n_fail} FALLOS | {n_warn} WARNINGS")
    print("=" * 70)

    if n_fail > 0:
        print()
        print("  FALLOS que debes resolver antes de arrancar:")
        for s, name, msg in results:
            if s == FAIL:
                print(f"  {FAIL} {name}")
                print(f"     → {msg}")
        print()
        print("  Resuelve los fallos y vuelve a ejecutar este script.")
    else:
        print()
        print("  Todo OK. Puedes arrancar el pipeline:")
        print("    python -m apps.trading_engine.main --once    (test)")
        print("    python -m apps.trading_engine.main           (continuo)")

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    # Imprimir cada check en tiempo real
    _original_check = check
    def check(name, fn):
        try:
            msg = fn()
            status = PASS
            results.append((PASS, name, msg or "OK"))
        except Exception as e:
            status = FAIL
            msg = str(e)
            results.append((FAIL, name, msg))
        print(f"  {status} {name}: {msg}")

    _original_warn = warn_check
    def warn_check(name, fn):
        try:
            msg = fn()
            status = PASS
            results.append((PASS, name, msg or "OK"))
        except Exception as e:
            status = WARN
            msg = str(e)
            results.append((WARN, name, msg))
        print(f"  {status} {name}: {msg}")

    sys.exit(main())
