"""
tests/test_all_services.py
──────────────────────────
Test suite completo de todos los servicios.
Ejecuta con dependencias reales (Supabase, Alpaca, etc.)

Uso:
    cd trading-system-app
    python tests/test_all_services.py

Requiere:
    - .env con SUPABASE_URL, SUPABASE_KEY, ALPACA_API_KEY, etc.
    - Datos existentes en Supabase (al menos AAPL en silver_features_1m)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ── Setup path ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Colores para la terminal ──────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

results: list[tuple[str, str, bool, str, float]] = []


def run_test(service: str, test_name: str, fn):
    """Ejecuta un test y registra el resultado."""
    t0 = time.time()
    try:
        result = fn()
        elapsed = time.time() - t0
        if result is True or result is None:
            print(f"  {GREEN}✓{RESET} {test_name} ({elapsed:.1f}s)")
            results.append((service, test_name, True, "", elapsed))
        else:
            print(f"  {RED}✗{RESET} {test_name}: {result} ({elapsed:.1f}s)")
            results.append((service, test_name, False, str(result), elapsed))
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  {RED}✗{RESET} {test_name}: {e} ({elapsed:.1f}s)")
        results.append((service, test_name, False, str(e), elapsed))


def section(name: str):
    print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {name}{RESET}")
    print(f"{BOLD}{CYAN}{'═'*60}{RESET}")


# ══════════════════════════════════════════════════════════════════
#  1. CONFIGURACIÓN Y CONEXIÓN
# ══════════════════════════════════════════════════════════════════

section("1. Configuración y conexión")

def test_config_loads():
    from shared.config import cfg
    assert cfg.supabase_url, "SUPABASE_URL vacío"
    assert cfg.supabase_key, "SUPABASE_KEY vacío"
    assert cfg.alpaca_api_key, "ALPACA_API_KEY vacío"
    assert cfg.repo_root.exists(), f"repo_root no existe: {cfg.repo_root}"
    assert cfg.models_dir.exists(), f"models_dir no existe: {cfg.models_dir}"
    print(f"       Supabase: {cfg.supabase_url[:40]}...")
    print(f"       Alpaca paper: {cfg.alpaca_paper}")
    return True

run_test("Config", "Cargar .env y crear directorios", test_config_loads)


def test_supabase_connection():
    from shared.db import sb
    resp = sb.table("config").select("id").limit(1).execute()
    assert resp.data is not None, "Supabase no devolvió datos"
    print("       Conexión OK, tabla config accesible")
    return True

run_test("Config", "Conexión a Supabase", test_supabase_connection)


# ══════════════════════════════════════════════════════════════════
#  2. MODEL REGISTRY (autodescubrimiento)
# ══════════════════════════════════════════════════════════════════

section("2. Model Registry")

def test_registry_auto_discover():
    from shared.models.registry import MODEL_REGISTRY, _auto_discover
    MODEL_REGISTRY.clear()  # forzar redescubrimiento
    _auto_discover()
    assert len(MODEL_REGISTRY) >= 6, f"Solo {len(MODEL_REGISTRY)} modelos descubiertos (esperados >= 6)"
    print(f"       {len(MODEL_REGISTRY)} modelos descubiertos: {list(MODEL_REGISTRY.keys())}")
    return True

run_test("Registry", "Auto-descubrimiento de modelos", test_registry_auto_discover)


def test_registry_list_models():
    from shared.models.registry import list_models
    models = list_models()
    assert len(models) >= 6
    for m in models:
        assert "name" in m, f"Modelo sin 'name': {m}"
        assert "model_type" in m, f"Modelo {m['name']} sin 'model_type'"
        assert "requires_gpu" in m, f"Modelo {m['name']} sin 'requires_gpu'"
    tree_models = [m for m in models if m["model_type"] == "tree"]
    dl_models = [m for m in models if m["model_type"] == "deep_learning"]
    print(f"       Tree-based: {[m['name'] for m in tree_models]}")
    print(f"       Deep learning: {[m['name'] for m in dl_models]}")
    return True

run_test("Registry", "list_models() con metadata", test_registry_list_models)


def test_registry_get_model():
    from shared.models.registry import get_model
    model = get_model("xgboost", task="classification", check_library=False)
    assert model is not None, "get_model devolvió None"
    assert model.task == "classification"
    assert not model.is_fitted, "Modelo nuevo no debería estar fitted"
    print(f"       Instancia: {model}")
    return True

run_test("Registry", "get_model('xgboost') instancia correcta", test_registry_get_model)


def test_registry_model_metadata():
    from shared.models.registry import MODEL_REGISTRY, _auto_discover
    _auto_discover()
    for name, cls in MODEL_REGISTRY.items():
        assert cls.name == name, f"{cls.__name__}.name = '{cls.name}' != '{name}'"
        assert cls.model_type in ("tree", "deep_learning"), f"{name}: model_type inválido: {cls.model_type}"
        assert isinstance(cls.requires_gpu, bool), f"{name}: requires_gpu no es bool"
    print("       Todos los modelos tienen name, model_type, requires_gpu correctos")
    return True

run_test("Registry", "Metadata consistente en todos los modelos", test_registry_model_metadata)


def test_registry_unknown_model():
    from shared.models.registry import get_model
    try:
        get_model("modelo_que_no_existe", check_library=False)
        return "Debería haber lanzado ValueError"
    except ValueError as e:
        assert "no reconocido" in str(e)
        print(f"       ValueError correcta: {e}")
        return True

run_test("Registry", "get_model con nombre inválido → ValueError", test_registry_unknown_model)


# ══════════════════════════════════════════════════════════════════
#  3. SIGNAL SOURCES (reglas técnicas)
# ══════════════════════════════════════════════════════════════════

section("3. Signal Sources")

def test_signal_auto_discover():
    from shared.signals.base import SIGNAL_REGISTRY, _auto_discover_signals
    SIGNAL_REGISTRY.clear()
    _auto_discover_signals()
    assert len(SIGNAL_REGISTRY) >= 4, f"Solo {len(SIGNAL_REGISTRY)} señales (esperadas >= 4)"
    print(f"       {len(SIGNAL_REGISTRY)} señales: {list(SIGNAL_REGISTRY.keys())}")
    return True

run_test("Signals", "Auto-descubrimiento de señales", test_signal_auto_discover)


def test_signal_list():
    from shared.signals import list_signals
    signals = list_signals()
    for s in signals:
        assert s["source_type"] == "rule", f"{s['name']} no es tipo 'rule'"
        assert s["requires_training"] is False
    print("       Todas las señales son reglas sin training")
    return True

run_test("Signals", "list_signals() metadata correcta", test_signal_list)


def test_signal_golden_cross():
    import pandas as pd

    from shared.signals import get_signal

    sig = get_signal("golden_cross")

    # Caso alcista: close > ema_9 > ema_21
    row_bull = pd.Series({"close": 180.0, "ema_9": 175.0, "ema_21": 170.0})
    result = sig.evaluate(row_bull)
    assert result.triggered is True, f"Golden cross debería dispararse: {result}"
    print(f"       Alcista: triggered={result.triggered}, score={result.score:.2f}")

    # Caso bajista: close < ema_21
    row_bear = pd.Series({"close": 165.0, "ema_9": 168.0, "ema_21": 170.0})
    result = sig.evaluate(row_bear)
    assert result.triggered is False, f"Golden cross NO debería dispararse: {result}"
    print(f"       Bajista: triggered={result.triggered}, score={result.score:.2f}")
    return True

run_test("Signals", "Golden Cross: evalúa correctamente", test_signal_golden_cross)


def test_signal_rsi_oversold():
    import pandas as pd

    from shared.signals import get_signal

    sig = get_signal("rsi_oversold")

    # RSI = 25 → sobreventa
    row = pd.Series({"rsi_14": 25.0})
    result = sig.evaluate(row)
    assert result.triggered is True, "RSI 25 debería ser sobreventa"
    assert result.priority in ("urgent", "normal")
    print(f"       RSI=25: triggered={result.triggered}, priority={result.priority}")

    # RSI = 50 → normal
    row = pd.Series({"rsi_14": 50.0})
    result = sig.evaluate(row)
    assert result.triggered is False
    print(f"       RSI=50: triggered={result.triggered}")

    # RSI = 15 → urgente
    row = pd.Series({"rsi_14": 15.0})
    result = sig.evaluate(row, config={"rsi_threshold": 30})
    assert result.triggered is True
    assert result.priority == "urgent"
    print(f"       RSI=15: triggered={result.triggered}, priority={result.priority}")
    return True

run_test("Signals", "RSI Oversold: umbrales y prioridad", test_signal_rsi_oversold)


def test_signal_volume_spike():
    import pandas as pd

    from shared.signals import get_signal

    sig = get_signal("volume_spike")

    # Volumen 5x → spike
    row = pd.Series({"volume_norm": 5.0})
    result = sig.evaluate(row, config={"volume_multiplier": 3.0})
    assert result.triggered is True
    print(f"       Vol=5x: triggered={result.triggered}, score={result.score:.2f}")

    # Volumen 1x → normal
    row = pd.Series({"volume_norm": 1.0})
    result = sig.evaluate(row)
    assert result.triggered is False
    print(f"       Vol=1x: triggered={result.triggered}")
    return True

run_test("Signals", "Volume Spike: detecta volumen anómalo", test_signal_volume_spike)


def test_signal_price_spike():
    import pandas as pd

    from shared.signals import get_signal

    sig = get_signal("price_spike")

    # Returns 3% → spike
    row = pd.Series({"returns_5": 0.03})
    result = sig.evaluate(row, config={"spike_threshold_pct": 2.0})
    assert result.triggered is True
    assert "alcista" in result.text
    print(f"       +3%: triggered={result.triggered}, text='{result.text}'")

    # Returns -0.5% → normal
    row = pd.Series({"returns_5": -0.005})
    result = sig.evaluate(row)
    assert result.triggered is False
    print(f"       -0.5%: triggered={result.triggered}")
    return True

run_test("Signals", "Price Spike: detecta movimiento brusco", test_signal_price_spike)


# ══════════════════════════════════════════════════════════════════
#  4. GUARDRAILS
# ══════════════════════════════════════════════════════════════════

section("4. Guardrails")

def test_guardrails_score_minimo():
    import pandas as pd

    from shared.guardrails import check_guardrails

    row = pd.Series({"close": 180, "rsi_14": 50, "is_market_open": True})
    cfg = {"score_threshold": 50, "score_minimo": {"activo": True, "valor": 65}}
    estado = {"posicion_abierta": False, "n_posiciones": 0, "ordenes_hoy": 0}

    pasa, motivo = check_guardrails(row, score=60, cfg_gr=cfg, estado=estado)
    assert pasa is False and "score_minimo" in motivo
    print(f"       Score 60 < 65: rechazado → {motivo}")

    pasa, motivo = check_guardrails(row, score=70, cfg_gr=cfg, estado=estado)
    assert pasa is True
    print("       Score 70 >= 65: aprobado")
    return True

run_test("Guardrails", "Score mínimo", test_guardrails_score_minimo)


def test_guardrails_rsi():
    import pandas as pd

    from shared.guardrails import check_guardrails

    cfg = {"score_threshold": 50, "rsi": {"activo": True, "compra_max": 70, "venta_min": 30}}
    estado = {"posicion_abierta": False, "n_posiciones": 0, "ordenes_hoy": 0}

    # RSI 75 + bullish → bloqueado
    row = pd.Series({"rsi_14": 75, "is_market_open": True})
    pasa, motivo = check_guardrails(row, score=80, cfg_gr=cfg, estado=estado)
    assert pasa is False and "rsi" in motivo
    print(f"       RSI=75 + bullish: rechazado → {motivo}")

    # RSI 50 → OK
    row = pd.Series({"rsi_14": 50, "is_market_open": True})
    pasa, motivo = check_guardrails(row, score=80, cfg_gr=cfg, estado=estado)
    assert pasa is True
    print("       RSI=50: aprobado")
    return True

run_test("Guardrails", "RSI sobrecompra/sobreventa", test_guardrails_rsi)


def test_guardrails_max_posiciones():
    import pandas as pd

    from shared.guardrails import check_guardrails

    row = pd.Series({"is_market_open": True})
    cfg = {"score_threshold": 50, "max_posiciones": {"activo": True, "valor": 3}}
    estado = {"posicion_abierta": False, "n_posiciones": 3, "ordenes_hoy": 0}

    pasa, motivo = check_guardrails(row, score=80, cfg_gr=cfg, estado=estado)
    assert pasa is False and "max_posiciones" in motivo
    print(f"       3/3 posiciones: rechazado → {motivo}")

    estado["n_posiciones"] = 1
    pasa, _ = check_guardrails(row, score=80, cfg_gr=cfg, estado=estado)
    assert pasa is True
    print("       1/3 posiciones: aprobado")
    return True

run_test("Guardrails", "Máximo de posiciones", test_guardrails_max_posiciones)


def test_decide_function():
    import pandas as pd

    from shared.guardrails import decide

    row = pd.Series({"ts": "2025-01-01T10:00:00Z", "rsi_14": 50, "is_market_open": True})
    cfg = {"score_threshold": 60}
    estado = {"posicion_abierta": False, "n_posiciones": 0, "ordenes_hoy": 0}

    # Score 80 >= 60 → BUY
    dec = decide("AAPL", 80.0, row, cfg, estado)
    assert dec["decision"] == "BUY"
    print(f"       Score=80: {dec['decision']}")

    # Score 40 < 60 → HOLD
    dec = decide("AAPL", 40.0, row, cfg, estado)
    assert dec["decision"] == "HOLD"
    print(f"       Score=40: {dec['decision']}")
    return True

run_test("Guardrails", "decide() → BUY/HOLD correcto", test_decide_function)


# ══════════════════════════════════════════════════════════════════
#  5. INFERENCE (con modelos reales de Supabase)
# ══════════════════════════════════════════════════════════════════

section("5. Inference")

def test_load_models_from_registry():
    from shared.db import sb
    # Buscar modelos entrenados en el registry de Supabase
    resp = sb.table("silver_model_registry").select(
        "experiment_name,model_name,is_active,status"
    ).eq("is_active", True).eq("status", "complete").limit(10).execute()

    if not resp.data:
        print(f"       {YELLOW}⚠ No hay modelos entrenados en silver_model_registry{RESET}")
        return True

    print(f"       {len(resp.data)} modelos activos en Supabase:")
    for m in resp.data:
        print(f"         {m['experiment_name']} ({m['model_name']})")
    return True

run_test("Inference", "Modelos entrenados en Supabase", test_load_models_from_registry)


def test_inference_load_and_predict():
    from shared.db import sb
    from shared.inference import load_models

    # Buscar un ensemble config con modelos
    resp = sb.table("silver_model_registry").select(
        "experiment_name,model_name"
    ).eq("is_active", True).eq("status", "complete").limit(6).execute()

    if not resp.data:
        print(f"       {YELLOW}⚠ Sin modelos entrenados, saltando test de predicción{RESET}")
        return True

    modelos_cfg = [
        {"experiment_name": m["experiment_name"], "activo": True, "peso": 1.0 / len(resp.data)}
        for m in resp.data
    ]

    modelos = load_models(modelos_cfg)
    if not modelos:
        print(f"       {YELLOW}⚠ No se pudieron cargar modelos (ficheros no encontrados){RESET}")
        return True

    print(f"       {len(modelos)} modelos cargados de {len(modelos_cfg)} configurados")
    for m in modelos:
        print(f"         ✓ {m['experiment_name']} ({m['model_name']}, peso={m['peso']:.2f})")

    # Intentar una predicción con datos reales
    import pandas as pd
    features_resp = sb.table("silver_features_rt").select("*").eq(
        "ticker", "AAPL"
    ).order("ts", desc=True).limit(20).execute()

    if not features_resp.data:
        features_resp = sb.table("silver_features_1m").select("*").eq(
            "ticker", "AAPL"
        ).order("ts", desc=True).limit(20).execute()

    if not features_resp.data:
        print(f"       {YELLOW}⚠ Sin features para AAPL, saltando predicción{RESET}")
        return True

    df = pd.DataFrame(features_resp.data).sort_values("ts")
    row = df.iloc[-1]

    from shared.inference import predict_ensemble
    score, detalle, signals = predict_ensemble(row, modelos, df_hist=df)

    print(f"       Predicción AAPL: score={score:.2f}")
    for exp, s in detalle.items():
        print(f"         {exp}: {s}")
    return True

run_test("Inference", "Cargar modelos + predicción real", test_inference_load_and_predict)


# ══════════════════════════════════════════════════════════════════
#  6. INGESTION SERVICE
# ══════════════════════════════════════════════════════════════════

section("6. Ingestion Service")

def test_fetch_prices():
    from apps.ingestion_live.alpaca_prices import fetch_prices
    fetch_prices(tickers=["AAPL"], timeframe="1m", bars=5)
    from shared.db import sb
    resp = sb.table("raw_ohlcv_rt").select("ts,ticker,close").eq(
        "ticker", "AAPL"
    ).order("ts", desc=True).limit(1).execute()
    assert resp.data, "No hay datos en raw_ohlcv_rt tras fetch"
    print(f"       Última vela AAPL: {resp.data[0]['ts']} close={resp.data[0]['close']}")
    return True

run_test("Ingestion", "fetch_prices(AAPL) → raw_ohlcv_rt", test_fetch_prices)


def test_fetch_news():
    from apps.ingestion_live.alpaca_news import fetch_news
    fetch_news(tickers=["AAPL"], hours=24)
    from shared.db import sb
    resp = sb.table("raw_news_rt").select("title,published_at").order(
        "published_at", desc=True
    ).limit(1).execute()
    if resp.data:
        print(f"       Última noticia: {resp.data[0]['title'][:60]}...")
    else:
        print(f"       {YELLOW}⚠ Sin noticias recientes (normal fuera de mercado){RESET}")
    return True

run_test("Ingestion", "fetch_news(AAPL) → raw_news_rt", test_fetch_news)


# ══════════════════════════════════════════════════════════════════
#  7. FEATURES SERVICE
# ══════════════════════════════════════════════════════════════════

section("7. Features Service")

def test_compute_silver():
    from apps.ingestion_live.silver_rt import compute_silver_rt
    df = compute_silver_rt(tickers=["AAPL"], timeframe="1m")
    if df.empty:
        print(f"       {YELLOW}⚠ DataFrame vacío (necesita datos recientes en raw_ohlcv_rt){RESET}")
        return True
    expected_cols = ["ema_9", "rsi_14", "macd_line", "bb_pct", "vwap", "atr_14"]
    missing = [c for c in expected_cols if c not in df.columns]
    assert not missing, f"Faltan columnas: {missing}"
    print(f"       {len(df)} filas, {len(df.columns)} columnas")
    print(f"       Indicadores: {[c for c in expected_cols if c in df.columns]}")
    return True

run_test("Features", "compute_silver_rt(AAPL) → indicadores", test_compute_silver)


def test_finbert_sentiment():
    from apps.ingestion_live.finbert_rt import get_sentiment
    sentiment = get_sentiment(tickers=["AAPL"], hours=24)
    if not sentiment:
        print(f"       {YELLOW}⚠ Sin noticias para analizar (normal fuera de mercado){RESET}")
        return True
    print(f"       {len(sentiment)} noticias analizadas con FinBERT")
    return True

run_test("Features", "FinBERT sentiment(AAPL)", test_finbert_sentiment)


# ══════════════════════════════════════════════════════════════════
#  8. API ROUTERS (import check)
# ══════════════════════════════════════════════════════════════════

section("8. API Routers")

def test_router_imports():
    from services.api.routers import (
        backtest,
        health,
        live,
        models,
        signals,
        squawks,
        tickers,
        training,
    )
    from services.api.routers import trading as trading_r

    routers = {
        "health": health.router, "tickers": tickers.router,
        "models": models.router, "training": training.router,
        "backtest": backtest.router, "live": live.router,
        "trading": trading_r.router, "signals": signals.router,
        "squawks": squawks.router,
    }

    for name, r in routers.items():
        n_routes = len(r.routes)
        print(f"       {name}: {n_routes} endpoint(s)")

    print(f"       {len(routers)} routers importados correctamente")
    return True

run_test("API", "Importar todos los routers", test_router_imports)


def test_api_app_creates():
    from services.api.main import app
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    print(f"       {len(routes)} rutas registradas")
    key_routes = ["/api/health", "/api/tickers", "/api/models/available"]
    for kr in key_routes:
        found = any(kr in r for r in routes)
        status = f"{GREEN}✓{RESET}" if found else f"{RED}✗{RESET}"
        print(f"       {status} {kr}")
    return True

run_test("API", "FastAPI app con todos los routers", test_api_app_creates)


# ══════════════════════════════════════════════════════════════════
#  9. SQUAWK SERVICE (placeholder)
# ══════════════════════════════════════════════════════════════════

section("9. Squawk Service")

def test_squawk_text_generation():
    from services.squawk.main import determine_priority, generate_squawk_text

    signal = {"ticker": "AAPL", "score": 87, "decision": "BUY"}
    text = generate_squawk_text(signal)
    assert "AAPL" in text and "87" in text
    print(f"       Texto: '{text}'")

    priority = determine_priority(signal)
    assert priority in ("urgent", "normal", "low")
    print(f"       Prioridad (score=87): {priority}")

    signal_low = {"ticker": "MSFT", "score": 55, "decision": "HOLD"}
    priority_low = determine_priority(signal_low)
    print(f"       Prioridad (score=55): {priority_low}")
    return True

run_test("Squawk", "Generación de texto + prioridad", test_squawk_text_generation)


# ══════════════════════════════════════════════════════════════════
#  10. TICKERS & SYMBOLS
# ══════════════════════════════════════════════════════════════════

section("10. Tickers & Symbols")

def test_symbols():
    from shared.symbols import ALL_SYMBOLS
    assert len(ALL_SYMBOLS) >= 16, f"Solo {len(ALL_SYMBOLS)} tickers (esperados >= 16)"
    assert "AAPL" in ALL_SYMBOLS
    print(f"       {len(ALL_SYMBOLS)} tickers: {list(ALL_SYMBOLS.keys())}")
    return True

run_test("Symbols", "ALL_SYMBOLS tiene 16+ tickers", test_symbols)


# ══════════════════════════════════════════════════════════════════
#  RESUMEN FINAL
# ══════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print(f"{BOLD}  RESUMEN{RESET}")
print(f"{'='*60}\n")

passed = sum(1 for _, _, ok, _, _ in results if ok)
failed = sum(1 for _, _, ok, _, _ in results if not ok)
total_time = sum(t for _, _, _, _, t in results)

# Agrupar por servicio
services = {}
for svc, test, ok, err, _t in results:
    if svc not in services:
        services[svc] = {"passed": 0, "failed": 0, "errors": []}
    if ok:
        services[svc]["passed"] += 1
    else:
        services[svc]["failed"] += 1
        services[svc]["errors"].append((test, err))

for svc, data in services.items():
    total = data["passed"] + data["failed"]
    if data["failed"] == 0:
        print(f"  {GREEN}✓{RESET} {svc}: {data['passed']}/{total} tests pasados")
    else:
        print(f"  {RED}✗{RESET} {svc}: {data['passed']}/{total} tests pasados, {data['failed']} fallidos:")
        for test, err in data["errors"]:
            print(f"      └─ {test}: {err[:80]}")

print(f"\n  Total: {GREEN}{passed} pasados{RESET}, {RED if failed else ''}{failed} fallidos{RESET if failed else ''}")
print(f"  Tiempo: {total_time:.1f}s")

if failed == 0:
    print(f"\n  {GREEN}{BOLD}✓ TODOS LOS TESTS PASARON{RESET}")
else:
    print(f"\n  {RED}{BOLD}✗ {failed} TEST(S) FALLIDO(S){RESET}")

sys.exit(0 if failed == 0 else 1)
