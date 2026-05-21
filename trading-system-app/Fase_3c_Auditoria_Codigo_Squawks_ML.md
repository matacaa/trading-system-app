# Fase 3c — Auditoría de código Squawks ML

## Objetivo

Revisar de forma estructurada cada función de cada script del repositorio `trading-system-app`. Entender qué hace cada pieza, cómo se conectan entre sí, validar que no hay errores, y diseñar guardrails de coste en Azure.

**Repo:** https://github.com/matacaa/trading-system-app
**Estado:** Fase 3b completada — sistema corriendo en Azure sin Supabase, 100% PostgreSQL directo (psycopg2).
**Producto:** Squawks ML es una app de alertas de trading (squawks), NO de ejecución de órdenes. El sistema detecta oportunidades, genera alertas con audio, y las envía al usuario, que decide si opera por su cuenta.

---

## Estructura del repositorio

### Carpetas principales

| Carpeta | Scripts | Qué hace en el sistema |
|---------|---------|----------------------|
| **`shared/`** | 43 | Todo lo que los demás importan. Conecta a PostgreSQL, lee variables de entorno, calcula indicadores técnicos, ejecuta los 6 modelos ML, genera las 25 señales de trading, y decide si una señal pasa los guardrails o se rechaza |
| **`apps/`** | 26 | Los procesos que corren en contenedores. El trading engine ejecuta el ciclo completo cada minuto. Ingestion live descarga precios y noticias en tiempo real. Ingestion historical hace lo mismo para datos pasados. ML sandbox entrena y evalúa modelos |
| **`services/`** | 15 | La API REST que expone el sistema al exterior. 20 endpoints FastAPI para consultar señales, trades, portfolio, modelos, velas, y activar/desactivar trading. Los 5 microservicios restantes son placeholders vacíos para fases futuras |
| **`tests/`** | 5 | Valida que indicadores, modelos y servicios funcionan correctamente. Incluye tests de paridad para asegurar que los cálculos históricos y en tiempo real dan el mismo resultado |
| **`workers/`** | 2 | Vacíos. Preparados para Fase 6, donde los backtests y entrenamientos se lanzarán como jobs asíncronos vía Azure Service Bus |
| **`scripts/`** | 1 | Verificación manual del sistema: comprueba que PostgreSQL responde, que hay datos recientes, que los modelos están registrados, y que la API contesta |

### Contenedores Docker en producción

| Contenedor | Dockerfile | Qué ejecuta | Qué código copia dentro |
|------------|-----------|-------------|------------------------|
| **squawks-api** | `Dockerfile.api` | `services/api/main.py` | `shared/` + `config/` + `services/api/` |
| **squawks-engine** | `Dockerfile.engine` | `apps/trading_engine/main.py` | `shared/` + `config/` + `apps/trading_engine/` + `apps/ingestion_live/` + `data/models/` |
| **squawks-ingestion** | `Dockerfile.ingestion` | `apps/ingestion_live/main.py` | `shared/` + `config/` + `apps/ingestion_live/` |

Sin Docker (ejecución manual local): `apps/ingestion_historical/`, `apps/ml_sandbox/`.

---

## Parte 1 — Revisión función por función — ✅ COMPLETADA

> **Orden de lectura:** respeta el grafo de dependencias. Nunca se revisa un script que llame a funciones de un archivo no revisado aún.
> 
> **12 bloques revisados** (A → L). 93 archivos auditados.

### Bloque A: Core compartido — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| A1 | `shared/config.py` | ✅ OK | Singleton con lru_cache, guardrail contra live trading, `_get()` no existe (doc estaba mal) |
| A2 | `shared/db.py` | ⚠️ Mejora | SQL injection en upsert (f-strings), sin retry automático |
| A3 | `shared/symbols.py` | ⚠️ Mejora | Datos duplicados (ALL_SYMBOLS y CATEGORIES), tickers hardcodeados vs YAML |
| A4 | `shared/utils/time.py` | ✅ OK | Zonas horarias centralizadas, reset diario correcto |
| A5 | `shared/utils/logging.py` | ✅ OK | Formato unificado, force=True correcto |
| A6 | `shared/indicators.py` | ⚠️ Mejora | SQL injection en enrich_sentiment, except Exception silencioso |
| A7 | `shared/guardrails.py` | ⚠️ Mejora | Variable row sobreescrita en guardrail 14, no hay SELL, config viene de YAML |

### Bloque B: Modelos ML — ✅ REVISADO (parcial)

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| B1 | `shared/models/base.py` | ✅ OK | Contrato bien definido, confidence_interval por modelo documentado |
| B2 | `shared/models/pytorch_models/dataset.py` | ✅ OK | Ventanas deslizantes, shuffle=False correcto, drop_last=False corregido |
| B3 | `shared/models/registry.py` | ⚠️ Mejora | Docstring dice Supabase, _auto_discover guard frágil |
| B4-B9 | 6 modelos individuales | — | Saltados (mismo patrón: heredan BaseModel, @register_model) |

### A★: Inference — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| A★ | `shared/inference.py` | ⚠️ Mejora | sklearn rellena features faltantes con 0 sin warning, score 50 por defecto puede triggear BUY, docstring dice Supabase |

### Bloque C: Señales técnicas — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| C1 | `shared/signals/base.py` | ✅ OK | Mismo patrón que modelos, preparado para config por usuario |
| C2-C26 | 25 reglas en `rules/` | ⚠️ Mejora | golden_cross usa EMAs no SMAs, scores hardcodeados no comparables entre señales |

### Bloque D: API FastAPI — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| D1 | `services/api/main.py` | ⚠️ Pendiente | CORS abierto, auth comentado |
| D2 | `routers/health.py` | ✅ OK | |
| D3 | `routers/signals.py` | ✅ OK | |
| D4 | `routers/live.py` | ⚠️ Mejora | POST /live/config escribe a filesystem efímero en Azure |
| D5 | `routers/models.py` | ✅ OK | |
| D6 | `routers/tickers.py` | ⚠️ Mejora | SQL injection en candles/historical, GET /tickers no escala a 500 |
| D7 | `routers/trading.py` | ⚠️ Pendiente | POST /trading/toggle sin autenticación |
| D8 | `routers/backtest.py` | 🔴 Roto parcial | POST /backtest roto: lazy import de `apps.api.main` (legacy Supabase) + subprocess a `ml_sandbox.backtest` (Supabase). GET /backtest/list funciona (usa `shared.db.query` psycopg2). Reescribir en Fase 6 |
| D9 | `routers/training.py` | 🔴 Roto parcial | POST /train roto: misma razón que D8 (lazy import + subprocess). Sin GET. Reescribir en Fase 6 |
| D10 | `routers/squawks.py` | — Placeholder | Fase 5 |

### Bloque E: Trading Engine — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| E1 | `apps/trading_engine/db.py` | ✅ OK | save_log tiene retry pero las demás funciones no (inconsistencia) |
| E2 | `apps/trading_engine/alpaca_trader.py` | ⚠️ Diseño | Solo BUY, no hay SELL explícito. Ventas vía bracket orders de Alpaca |
| E3 | `apps/trading_engine/reconciliation.py` | ✅ OK | Cubre fills, SL/TP, cancelaciones, cierres manuales |
| E4 | `apps/trading_engine/main.py` | ⚠️ Mejora | Docstring dice Supabase, config de filesystem efímero, modelos sin recarga en caliente |
| E5 | `apps/trading_engine/trading_engine_main.py` | 🔴 Duplicado | Copia exacta de E4, pendiente borrar |

### Bloque F: Ingestion Live — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| F1 | `apps/ingestion_live/main.py` | ✅ OK | |
| F2 | `apps/ingestion_live/alpaca_prices.py` | ✅ OK | |
| F3 | `apps/ingestion_live/alpaca_news.py` | ⚠️ Escala mal | Descarga en bucle por ticker, no escala a 500 |
| F4 | `apps/ingestion_live/finbert_rt.py` | ⚠️ Escala mal | Procesa titular por titular, batch sería más rápido |
| F5 | `apps/ingestion_live/silver_rt.py` | ⚠️ Mejora | Conteo noticias O(n×m), docstring dice Supabase |

### Bloque G: Ingestion Historical — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| G1 | `apps/ingestion_historical/main.py` | ✅ OK | Solo orquesta |
| G2 | `apps/ingestion_historical/downloader.py` | ✅ OK | Solo descarga de yfinance |
| G3 | `apps/ingestion_historical/ingestion.py` | 🔴 Usa Supabase | No migrado |
| G4 | `apps/ingestion_historical/silver.py` | 🔴 Usa Supabase | No migrado |
| G5 | `apps/ingestion_historical/finbert.py` | 🔴 Usa Supabase | No migrado |
| G6 | `apps/ingestion_historical/news_alpaca.py` | 🔴 Usa Supabase | No migrado |
| G7 | `apps/ingestion_historical/tensor.py` | 🔴 Eliminar | Usa Supabase + redundante con dataset.py |

### Bloque H: ML Sandbox — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| H1 | `apps/ml_sandbox/pipeline.py` | ✅ OK | Solo orquesta, no toca base de datos |
| H2 | `apps/ml_sandbox/config.py` | 🔴 Usa Supabase | Accede a app_cfg.supabase_url/key que ya no existen → AttributeError al arrancar |
| H3 | `apps/ml_sandbox/data/loader.py` | 🔴 Usa Supabase | Carga datos vía sb.table(). Tiene path a tensores que vamos a eliminar |
| H4 | `apps/ml_sandbox/data/splitter.py` | 🔴 Usa Supabase | Split temporal correcto pero importa sb |
| H5 | `apps/ml_sandbox/train.py` | 🔴 Usa Supabase | Fix F-50 correcto (guarda antes de borrar). Registra en silver_model_registry vía sb |
| H6 | `apps/ml_sandbox/evaluate.py` | 🔴 Usa Supabase | Métricas correctas, guarda en silver_metrics y silver_predictions vía sb |
| H7 | `apps/ml_sandbox/backtest.py` | 🔴 Usa Supabase | 518 líneas. Usa shared/guardrails e inference (correcto). Guarda resultados vía sb |

### Bloque I: Infra y Docker — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| I1 | `docker/Dockerfile.base` | ⚠️ Mejora | torch en requirements.txt sin flag CPU-only; funciona porque se instala antes con `--index-url cpu`, pero si pip decidiera actualizar descargaría CUDA (~2GB). Imagen base no pineada (python:3.11-slim puede cambiar entre builds) |
| I2 | `docker/Dockerfile.api` | ⚠️ Mejora | Instala fastapi/uvicorn que ya están en requirements.txt (redundante). `--workers 2` OK para dev, en Azure conviene 1 (escalar por réplica). HEALTHCHECK bien configurado |
| I3 | `docker/Dockerfile.engine` | ⚠️ Mejora | HEALTHCHECK solo verifica import, no que el scheduler esté vivo ni que haya conexión a PostgreSQL. Modelos horneados en imagen (pendiente #13 Blob Storage). Copia `apps/ingestion_live/` porque el engine importa directamente de ahí (acoplamiento fuerte pero necesario) |
| I4 | `docker/Dockerfile.ingestion` | ✅ OK | Pre-cachea FinBERT en build time (ahorra ~100s). start_period=120s generoso para carga inicial. Mismo tema del HEALTHCHECK que solo verifica import |
| I5 | `docker-compose.dev.yml` | ⚠️ Mejora | Falta volumen `apps/ingestion_live` en engine (el engine importa de ahí pero no lo monta, cambios en dev no se reflejan). depends_on apunta a API pero la dependencia real es PostgreSQL (no está en el compose). No hay servicio PostgreSQL para dev local autosuficiente. Hot-reload de API bien configurado |
| I6 | `.github/workflows/ci.yml` | 🔴 Bug | Escucha en rama `main` pero la rama principal es `master` → **CI nunca se ejecuta**. Env vars de Supabase legacy (SUPABASE_URL/KEY como placeholder). `pip install -e ".[dev]"` instala supabase como dependencia porque sigue en pyproject.toml |
| I7 | `.github/workflows/deploy.yml` | ⚠️ Mejora | Trigger en `master` (correcto). Buildea imagen base sin cachear → rebuild completo en cada deploy (~10min). No hay rollback automático. Double tagging (latest + sha) correcto |
| I8 | `.dockerignore` | 🔴 Bug | **Merge conflict sin resolver** (marcadores `<<<<<<<`, `=======`, `>>>>>>>` en líneas 30-38). Docker los ignora silenciosamente y el resultado funcional es correcto (modelos no se excluyen), pero el archivo tiene basura. Resto del ignore correcto |
| I9 | `requirements.txt` | ⚠️ Mejora | Desincronizado con pyproject.toml: tiene `psycopg2-binary` que no está en pyproject; no tiene `supabase` que sí está en pyproject. `torch>=2.1` sin restricción CPU-only |
| I10 | `pyproject.toml` | ⚠️ Mejora | `supabase>=2.3` sigue como dependencia (ya no se usa, eliminar). Falta `psycopg2-binary` que sí se usa. Sección `[tool.setuptools.packages.find]` no incluye `services*` (import puede fallar fuera de Docker). Extras `dashboard` referencia Streamlit que ya no existe |

### Bloque J: YAMLs de configuración — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| J1 | `config/live/ensemble.yaml` | 🔴 Bug | Pesos suman 1.15 (pendiente #1). Tiene 7 entradas pero solo 6 modelos: `aapl_rf_1m_v1` (peso 0.20) y `aapl_random_forest_1m_v1` (peso 0.15) son el mismo modelo listado dos veces. La entrada `aapl_random_forest_1m_v1` no existe como experiment en ningún otro lugar del repo. Solo AAPL como ticker. 14 guardrails configurables, solo 2 activos (horario_mercado y posicion_abierta). score_threshold=50 |
| J2 | `config/live/trading.yaml` | ✅ OK | Minimal: interval 1min, apunta a ensemble.yaml. Contiene guardrail: si alguien cambia el path a un backtest config, lo detecta |
| J3 | `config/ingestion/tickers.yaml` | ⚠️ Código muerto | Solo tiene AAPL. Ningún archivo Python lo lee — los tickers vienen de `shared/symbols.py` o del ensemble YAML. Config inerte |
| J4 | `config/experiments/aapl_transformer_1m_v2.yaml` | ⚠️ Mejora | Filename dice `v2` pero `experiment.name` dice `v1`. Train: 5 días (Apr 10-15), test: 1 día (Apr 16-17). 12 features, classification, target_threshold=0. `ml_sandbox/config.py` referencia `aapl_xgboost_1m.yaml` (sin v2) que no existe |
| J5 | `config/experiments/aapl_gru_1m_v2.yaml` | ⚠️ Mejora | Mismo patrón: filename v2, name v1. Mismas fechas y features que J4 |
| J6 | `config/experiments/aapl_lstm_1m_v2.yaml` | ⚠️ Mejora | Mismo patrón |
| J7 | `config/experiments/aapl_lgbm_1m_v2.yaml` | ⚠️ Mejora | Mismo patrón. Sin sección `pytorch` (correcto, es sklearn) |
| J8 | `config/experiments/aapl_rf_1m_v2.yaml` | ⚠️ Mejora | Mismo patrón |
| J9 | `config/experiments/aapl_xgboost_1m_v2.yaml` | ⚠️ Mejora | Mismo patrón |
| J10 | `config/backtests/aapl_backtest_v1.yaml` | ✅ OK | Pesos suman 1.0 (correcto). 6 modelos (sin el duplicado RF). Solo referenciado desde ml_sandbox/backtest.py (roto por Supabase) |

### Bloque K: Tests y scripts — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| K1 | `tests/conftest.py` | ⚠️ Mejora | `day1.append(day2)` usa API deprecated de pandas (usar `pd.concat([day1, day2])`) . Fixtures bien diseñados: sample_ohlcv (100 barras, 1 día) y multiday_ohlcv (780 barras, 2 días) |
| K2 | `tests/shared/test_indicators.py` | ✅ OK | 3 smoke tests: EMA no rompe, RSI en rango, VWAP positivo. TODOs de Fase 3.4 pendientes |
| K3 | `tests/shared/test_models.py` | ✅ OK | Cobertura sólida: 11 tests para BaseModel, sklearn (XGB, RF, LGB) y PyTorch (LSTM, GRU, Transformer). Verifica fit/predict/proba/save/load/confidence_interval |
| K4 | `tests/shared/test_parity.py` | ⚠️ Roto parcial | Tests de corrección excelentes (RSI Wilder vs SMA, VWAP reset vs cumulative, ATR EMA vs SMA, log_returns vs pct_change). Pero `TestSilverParity.test_calc_features_parity` importa `apps.ingestion_historical.silver.calc_features` que usa Supabase → falla en import. Los demás tests corren sin DB |
| K5 | `tests/test_all_services.py` | 🔴 Usa Supabase | 437 líneas. Suite completa de 18+ tests que cubren config, registry, signals, guardrails, inference, ingestion, features, API, squawk, symbols. Pero todo vía `sb.table()`. No es un pytest: se ejecuta como script (`python tests/test_all_services.py`). Framework propio de reporting con colores. Hay que reescribirlo completo para psycopg2 (pendiente #15) |
| K6 | `scripts/verify_system.py` | 🔴 Usa Supabase | 27 checks de pre-arranque: Python version, imports, config, Supabase schema, modelos, Alpaca, datos recientes. Todo vía `sb.table()`. Path hardcodeado a Windows (`C:\Users\jgrma\Desktop`). Migrar a psycopg2 (pendiente #16) |
| K7 | `scripts/schema_fixes.sql` | ⚠️ Legacy | SQL válido y útil (índices, constraints, columnas nuevas). Escrito para el panel SQL de Supabase pero funciona en PostgreSQL directo. Sirve como documentación del schema. Nota: la tabla `config` definida aquí es de la era Supabase — el sistema actual la gestiona diferente |

### Bloque L: Placeholders — ✅ REVISADO

| # | Archivo | Veredicto | Notas |
|---|---------|-----------|-------|
| L1 | `workers/backtest/main.py` | — Placeholder | 70 líneas. Docstring describe flujo futuro: Service Bus → cacheo inteligente (si solo cambian guardrails, reutilizar predicciones). Stub con TODO Fase 4 |
| L2 | `workers/training/main.py` | — Placeholder | 61 líneas. Flujo futuro: cola → descarga datos → generar tensores → entrenar → Blob Storage → registry → invalidar cache → notificar. Stub |
| L3 | `services/decision/main.py` | — Placeholder | 49 líneas. Separa inference de decision para habilitar cacheo. Escuchará evento `signals_ready` |
| L4 | `services/features/main.py` | — Placeholder | 83 líneas. Feature engine compartido. Escuchará `ingestion_complete`. Tiene esqueleto de scheduler |
| L5 | `services/inference/main.py` | — Placeholder | 59 líneas. Iterará usuarios activos con batching por modelo+ticker |
| L6 | `services/ingestion/main.py` | — Placeholder | 82 líneas. Container App always-on. Publicará `ingestion_complete`. Esqueleto de scheduler |
| L7 | `services/squawk/main.py` | ⚠️ Parcial | Tiene `generate_squawk_text()` y `determine_priority()` funcionales (usadas en K5). TODOs para Azure Speech TTS, Blob Storage, SignalR, Notification Hubs |

---

## Parte 2 — Revisión de arquitectura (SIGUIENTE)

1. Flujo de datos completo: Alpaca → raw_ohlcv_rt → silver_features_rt → inference → gold_signals → gold_decisions → squawks
2. Diagrama de dependencias entre módulos
3. Tablas PostgreSQL: las ~22 tablas, sus relaciones, índices
4. Ciclo de vida de una señal: desde que se genera hasta que se convierte en squawk
5. Puntos de fallo: qué pasa si Alpaca cae, si PostgreSQL no responde, si un modelo falla
6. Duplicados y código muerto

---

## Parte 3 — Azure: servicios, configuración y guardrails de coste (PENDIENTE)

### 3.1 — Inventario de servicios Azure activos

| Servicio | Recurso | Revisar |
|----------|---------|---------|
| **Resource Group** | `squawks-ml` | Región, tags |
| **Container Registry** | ACR (Basic) | SKU, imágenes, retention policy |
| **PostgreSQL Flexible Server** | `squawks-ml-db` | SKU (B1ms), almacenamiento, backups, firewall, conexiones max |
| **Container Apps** | api, engine, ingestion | CPU/memoria, replicas, env vars, health probes |
| **Container Apps Environment** | Entorno compartido | VNet, logs |
| **Log Analytics Workspace** | (automático) | Retención, ingesta diaria, coste oculto |

### 3.2 — Guardrails de coste Azure

| Guardrail | Qué protege | Cómo |
|-----------|-------------|------|
| Budget alert | Gasto total | Alertas a 30€, 40€, 50€ |
| PostgreSQL storage cap | Disco sin control | Desactivar auto-grow o límite |
| PostgreSQL connection limit | Pool desbordado | maxconn=10 vs límite servidor |
| ACR image retention | Imágenes acumuladas | Mantener últimas 5-10 |
| Container Apps max replicas | Escalado excesivo | Max 1 engine/ingestion, 2-3 API |
| Log Analytics daily cap | Ingesta cara | Cap 0.5 GB/día |
| Container Apps idle | Contenedores parados | Min replicas = 0 donde posible |

### 3.3 — Estimación de coste

| Servicio | Estimación |
|----------|-----------|
| PostgreSQL Flexible (B1ms) | ~12-15€/mes |
| Container Apps (3 servicios) | ~8-12€/mes |
| ACR Basic | ~5€/mes |
| Log Analytics | ~2-5€/mes |
| Bandwidth | ~1-2€/mes |
| **Total estimado** | **~28-39€/mes** |

---

## Pendientes técnicos — 49 puntos

### Arreglados durante la auditoría (Fase 3c) — 16 puntos ✅

| # | Qué | Estado |
|---|-----|--------|
| 1 | Pesos del ensemble suman 1.15 — entrada fantasma `aapl_random_forest_1m_v1` eliminada, 6 modelos suman 1.0 | ✅ Arreglado |
| 2 | golden_cross docstring decía SMA pero usaba EMA — docstring y variables corregidos | ✅ Arreglado |
| 3 | CORS abierto `["*"]` — ahora lee `CORS_ORIGINS` de env var, default `localhost:3000` | ✅ Arreglado |
| 4 | main.py duplicado — `trading_engine_main.py` pendiente de borrar (no incluido en zip) | 🗑️ Borrar |
| 5 | Código muerto — `debug_news.py` y `tensor.py` pendientes de borrar. `apps/api/main.py` NO borrar aún (D8/D9 dependen) | 🗑️ Borrar parcial |
| 6 | Retry con backoff en db.py — `get_conn()` ahora tiene 3 reintentos con backoff exponencial para errores transitorios | ✅ Arreglado |
| 7 | tensor.py redundante — pendiente de borrar (no incluido en zip) | 🗑️ Borrar |
| 8 | Docstrings dicen "Supabase" — cambiados a "PostgreSQL" en engine/main.py, silver_rt.py, registry.py, inference.py | ✅ Arreglado |
| 9 | Merge conflict en .dockerignore — marcadores `<<<<<<<`/`>>>>>>>` eliminados | ✅ Arreglado |
| 10 | CI en rama `main` inexistente — cambiado a `master`. Env vars Supabase reemplazadas por DATABASE_URL | ✅ Arreglado |
| 11 | `supabase>=2.3` en pyproject.toml — reemplazado por `psycopg2-binary>=2.9` | ✅ Arreglado |
| 12 | requirements.txt y pyproject.toml desincronizados — pyproject ahora incluye psycopg2-binary y `services*` en packages | ✅ Arreglado |
| 13 | Falta volumen ingestion_live en engine del compose — añadido | ✅ Arreglado |
| 14 | RF duplicado en ensemble.yaml — eliminado (cubierto por #1) | ✅ Arreglado |
| 15 | Filenames experiments v2 / name v1 — experiment.name actualizado a v2 en los 6 archivos | ✅ Arreglado |
| 16 | conftest .append() deprecated — reemplazado por DatetimeIndex concat | ✅ Arreglado |

### Aplazados a Fase 6 — 22 puntos

| # | Qué | Contexto |
|---|-----|----------|
| 17 | Routers backtest y training rotos | POST roto: lazy import de `apps/api/main.py` (legacy 597 líneas Supabase) + subprocess a ml_sandbox (Supabase). GET /backtest/list funciona. NO borrar `apps/api/main.py` hasta reescribir D8/D9 con Service Bus + workers |
| 18 | `test_all_services.py` reescribir completo | 437 líneas, 18+ tests, todo vía sb.table(). Migrar a psycopg2, cubrir todos los servicios y flujos |
| 19 | `verify_system.py` migrar a psycopg2 | 27 checks, todo vía sb.table(). Path hardcodeado a Windows. Actualizar sin Supabase |
| 20 | Bloques G y H completos: 11 de 14 archivos usan Supabase | ingestion.py, silver.py, finbert.py, news_alpaca.py, tensor.py (G) + config.py, loader.py, splitter.py, train.py, evaluate.py, backtest.py (H). Pipeline histórico y ML sandbox enteros rotos |
| 21 | Almacenamiento persistente | Azure Blob Storage para modelos entrenados por usuario + recarga en caliente |
| 22 | Escalado PostgreSQL multi-usuario | Separar tablas compartidas (predicciones) de tablas por usuario (decisiones). Evaluar guardrails en memoria, escribir batch. Planificar salto SKU B1ms → General Purpose (200-300 usuarios) |
| 23 | Pool de 500 tickers | Ampliar de 16 a 500. Ingesta de los 500, inferencia solo para los que alguien sigue |
| 24 | Selección de tickers por usuario | Cada usuario elige qué tickers seguir del catálogo |
| 25 | Guardrails personalizados por usuario POR ticker | Cada combinación user+ticker tiene su config. Tabla `user_guardrails` en vez de YAML |
| 26 | Usuarios pueden entrenar sus propios modelos | Eligen fechas train/test, worker entrena, modelo se guarda en Blob Storage por user_id. Guardrails sobre el entrenamiento: mínimo 3 meses train, 1 mes test |
| 27 | Inferencia por usuario | Si un usuario tiene modelos propios, la inferencia ya no es compartida. Cada usuario con modelos custom necesita su propia ejecución de predicción por ticker. Usuarios sin modelos propios usan los del sistema como default |
| 28 | Config del ensemble en filesystem efímero | En Azure, si el contenedor se reinicia los cambios vía API se pierden. Mover a base de datos |
| 29 | Auth inexistente | Routers de auth y user comentados. POST /trading/toggle sin protección. Necesario antes de producción |
| 30 | GET /tickers no escala a 500 | Hace una query por ticker. Debería ser `SELECT DISTINCT` |
| 31 | Noticias descargadas en bucle por ticker | No escala a 500, necesita batching o paralelismo |
| 32 | FinBERT procesa titular por titular | Batch sería más rápido con muchos tickers |
| 33 | Conteo de noticias O(n×m) en silver_rt.py | Optimizar con merge_asof |
| 34 | Inconsistencia en retry | save_log tiene retry (3 intentos), save_signals/save_decision/save_timing no |
| 35 | Modelos se cargan una vez al arrancar | Si reentrenas un modelo, el engine no lo recoge hasta reiniciar el contenedor |
| 36 | HEALTHCHECKs de engine e ingestion solo verifican import | No detectan si el scheduler está colgado o PostgreSQL caído. Mejorar con endpoint HTTP o fichero de heartbeat |
| 37 | tickers.yaml nunca se lee desde Python | `config/ingestion/tickers.yaml` es config inerte. Decidir: eliminar o integrar como fuente única de tickers |
| 38 | test_parity importa de silver.py (Supabase) → falla | `tests/shared/test_parity.py` TestSilverParity. Los tests de corrección funcionan, el de paridad no importa |

### Mejoras de código (no urgentes) — 11 puntos

| # | Qué | Dónde |
|---|-----|-------|
| 39 | SQL injection en upsert y enrich_sentiment | `shared/db.py`, `shared/indicators.py` — nombres de tabla con f-strings |
| 40 | SQL injection en candles/historical | `services/api/routers/tickers.py` — timeframe del usuario en nombre de tabla |
| 41 | except Exception silencioso en indicators.py | Errores en consultas de sentiment se tragan sin log |
| 42 | Variable `row` sobreescrita en guardrail 14 | `shared/guardrails.py` — circuit breaker reasigna `row`. Trampa si se añaden guardrails después |
| 43 | No hay flujo de SELL explícito | El sistema solo decide BUY o HOLD. Ventas dependen de bracket orders de Alpaca. Decisión de diseño a documentar |
| 44 | Datos duplicados en symbols.py | ALL_SYMBOLS y CATEGORIES repiten info. Fuente única debería ser CATEGORIES |
| 45 | Tickers hardcodeados vs YAML | Dos fuentes de verdad: symbols.py y tickers.yaml |
| 46 | _predict_sklearn rellena features faltantes con 0 sin warning | `shared/inference.py` — _predict_pytorch sí loguea, sklearn no |
| 47 | Score por defecto 50 cuando todos los modelos fallan puede triggear BUY | `shared/inference.py` — si score_threshold está en 50, un fallo total genera señal falsa |
| 48 | _auto_discover() guard frágil en registry y signals | Si un modelo/señal se registra manualmente antes del auto-discover, el guard corta. Usar flag booleano |
| 49 | Scores de señales hardcodeados y no comparables | golden_cross siempre 0.8, rsi_oversold proporcional. Cada señal usa su propia escala |

---

## Estadísticas del repo (verificadas contra el repo clonado)

- **121 archivos Python** (~10,946 líneas)
- **366 funciones** (def + async def)
- **59 clases**
- **13 archivos YAML/YML**
- **4 Dockerfiles** + docker-compose + 2 workflows CI/CD
- **~22 tablas PostgreSQL** (3 raw, 8 silver, 5 gold, 3 backtest, 3 otros)
- **6 modelos ML entrenados** (Transformer, GRU, LSTM, LightGBM, RF, XGBoost)
- **25 señales técnicas** (reglas rule-based)
- **3 servicios Docker** (API, engine, ingestion)

---

## Formato de la auditoría

Para cada archivo, seguir este formato:

```
### [ID] archivo.py

**Propósito:** qué hace este archivo en una frase

**Funciones:**
- `nombre_funcion(params)` → qué devuelve
  - Línea X: qué hace esta parte
  - Línea Y: posible mejora / bug detectado

**Dependencias:** de quién importa, quién lo importa

**Veredicto:** ✅ OK / ⚠️ Mejora sugerida / 🔴 Bug
```
