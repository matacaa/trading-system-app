# AUDITORÍA POST-FIX — trading-system

**Fecha**: 26 abril 2026
**Scope**: Re-lectura exhaustiva de los 104 ficheros del ZIP entregado
**Foco especial**: inserts/upserts a tablas Supabase

---

## Resumen

| Categoría | Cantidad |
|---|---|
| Regresiones introducidas por los fixes | 1 |
| Issues pendientes con impacto en inserts a tablas | 7 |
| Issues pendientes sin impacto en inserts | ~55 |
| Issues cosmético/bajo riesgo | ~12 |

---

## 1. REGRESIÓN INTRODUCIDA

### R-01: silver.py escribe `sentiment_label_encoded` a tablas que no tienen esa columna (CRÍTICO)

**Fichero**: `apps/ingestion_historical/silver.py` línea 197
**Tabla afectada**: `silver_features_1m`, `silver_features_5m`, `silver_features_15m`

`save_silver()` incluye `sentiment_label_encoded` en la lista de columnas a escribir. Pero según el schema documentado, esa columna solo existe en `silver_features_rt`, NO en las tablas históricas.

Cuando el pipeline histórico ejecute `run_silver()`, el upsert enviará un campo que la tabla no reconoce. PostgREST puede:
- Ignorarlo silenciosamente (poco probable)
- Devolver error 400 (probable → el batch entero falla)

**Fix**: Añadir a `scripts/schema_fixes.sql`:
```sql
ALTER TABLE silver_features_1m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
ALTER TABLE silver_features_5m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
ALTER TABLE silver_features_15m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
```

---

## 2. ISSUES PENDIENTES CON IMPACTO EN INSERTS A TABLAS

### I-01: `category` nunca se escribe en silver_features_1m/5m/15m

**Fichero**: `apps/ingestion_historical/silver.py`
**Schema**: `silver_features_1m` tiene columna `category` (varchar)
**Código**: `calc_features()` no calcula `category`. `save_silver()` no lo incluye en `cols`.
**Resultado**: Columna siempre NULL.
**Fix**: Añadir `out["category"] = SYMBOL_CATEGORY.get(ticker, "unknown")` en `calc_features()` usando `shared.symbols.SYMBOL_CATEGORY`.

### I-02: `silver_features_rt` no escribe `news_count_1h`, `news_count_24h`, `has_news`

**Fichero**: `apps/ingestion_live/silver_rt.py`
**Impacto parity**: Si un modelo se entrena con datos históricos que SÍ tienen news_count (tras el fix D-08/N-22), pero en live esas features no existen en `silver_features_rt`, inference.py las rellenará con 0.
**Fix**: Dos opciones:
1. Añadir las columnas a `silver_features_rt` (SQL) y calcularlas en `compute_silver_rt()`
2. Asegurar que los yamls de modelos no incluyan esas features en `columns`

### I-03: `close_all()` no escribe `precio_salida`, `pnl`, `pnl_pct` en gold_trades

**Fichero**: `apps/trading_engine/alpaca_trader.py` líneas 226-230
**Qué escribe**: `ts_salida`, `motivo_salida="close_all_emergencia"`, `status="closed"`
**Qué NO escribe**: `precio_salida`, `pnl`, `pnl_pct`
**Resultado**: Trades cerrados por emergencia quedan con P&L NULL. Dashboard no puede calcular resultado.
**Fix**: Leer `market_value` de cada posición antes de cerrarla y calcular P&L.

### I-04: `save_decision` primer guardado siempre con `ejecutada=False`

**Fichero**: `apps/trading_engine/db.py` + `apps/trading_engine/main.py`
**Flujo**: decide() → save_decision(ejecutada=False) → execute_order() → save_decision(ejecutada=True). Si execute_order falla entre el submit y el save, `gold_decisions` queda con `ejecutada=False` para una orden que SÍ se envió a Alpaca.
**Impacto**: Datos de auditoría inconsistentes con realidad.
**Fix menor**: Aceptable como trade-off. Documentar que `ejecutada=False` + `decision=BUY` puede significar "intentado pero no confirmado".

### I-05: Backtest `save_results` DELETE sin transacción

**Fichero**: `apps/ml_sandbox/backtest.py` líneas 310-312
**Qué hace**: DELETE de backtest_trades, backtest_metrics, backtest_runs → INSERT nuevos.
**Riesgo**: Si el INSERT falla después del DELETE, se pierde el backtest anterior.
**Mitigación aplicada**: El código ahora hace DELETE primero y tiene tracking de batches fallidos (F-04). Pero no es atómico.
**Fix completo**: Usar DELETE solo después de verificar que el INSERT principal funcionó, o usar nombres temporales.

### I-06: `gold_logs.run_id` puede no existir en Supabase

**Fichero**: `apps/trading_engine/db.py` línea 85
**Schema documentado**: gold_logs no lista `run_id` como columna
**Fix**: Ya incluido en `schema_fixes.sql` (ALTER TABLE ADD COLUMN IF NOT EXISTS). El usuario debe ejecutar el SQL.

### I-07: Nombre tabla `ingestion_log` vs `ingestion_logs`

**Fichero**: `apps/ingestion_historical/ingestion.py` línea 96
**Código actual**: `sb.table("ingestion_log")` (singular, post-fix N-07)
**Riesgo**: Si la tabla real en Supabase se llama `ingestion_logs` (plural), cada insert falla silenciosamente dentro del try/except.
**Fix**: Verificar en Supabase con `SELECT table_name FROM information_schema.tables WHERE table_name IN ('ingestion_log', 'ingestion_logs')` y alinear.

---

## 3. ISSUES PENDIENTES SIN IMPACTO DIRECTO EN INSERTS

### Código: issues que afectan lógica pero no escritura a tablas

| ID | Issue | Fichero | Severidad |
|---|---|---|---|
| F-11 | Sin threshold de salida por score | guardrails.py | Medio |
| F-13 | Intervalo 1 min puede ser insuficiente | main.py | Medio |
| F-35 | MarketOrderRequest con bracket — verificar API | alpaca_trader.py | Medio |
| F-44 | library.active no bloquea uso en live | registry.py | Bajo |
| F-78 | Sin atomicidad raw→silver | silver.py | Medio |
| F-82 | Upsert 100 filas cuando solo ~1 es nueva | silver_rt.py | Bajo |
| F-83 | Returns NaN en primeras barras de warm-up | silver.py/silver_rt.py | Bajo |
| F-84 | compute_indicators no agrupa por ticker | silver_rt.py | Medio |
| F-103 | Paginación acumula todo en memoria | loader.py | Bajo |
| F-104 | load_data query por ticker (N queries) | loader.py | Bajo |
| F-105 | Sin cache de datasets | loader.py | Bajo |
| A-03 | Modelos cargados una sola vez al arrancar | main.py | Bajo |

### Schema/BBDD: issues que requieren SQL

| ID | Issue | Fix en schema_fixes.sql |
|---|---|---|
| D-01/D-06 | Tablas legacy kpis | ✅ Incluido (comentado) |
| D-02 | Naming mix inglés/español | No fixable via SQL |
| D-07 | raw_ohlcv_rt schema distinto | Requiere migración |
| D-09 | silver_features_rt sin id | ✅ Incluido |
| D-10 | Tablas duplicadas predictions/signals | Decisión arquitectónica |
| D-12 | Sin FK gold_trades→gold_decisions | Decisión arquitectónica |
| D-13 | backtest_trades mezcla trades y rechazos | Decisión arquitectónica |
| D-19 | Sin FKs entre tablas | Decisión arquitectónica |

### Tests pendientes

| ID | Issue |
|---|---|
| F-110 | Sin tests para BaseModel |
| — | Sin tests de integración para inserts a Supabase |
| — | Sin tests para reconciliation.py |
| — | Sin tests para backtest.py (solo indicators y parity) |

### Cosmético/documentación

| ID | Issue |
|---|---|
| F-15 | Delay intrínseco vela vs decisión (inherente) |
| F-106 | .values en vez de .to_numpy() |
| O-23 | Docstring "26 indicadores" incorrecto |
| — | enrich_sentiment tiene if/else con ramas idénticas (código muerto) |
| — | Docstrings de indicators.py aún dicen "silver_rt.py actual usa SMA" (ya corregido) |

---

## 4. MAPA COMPLETO: TABLA → INSERTS/UPSERTS → ESTADO

| Tabla | Operación | Fichero | Campos | Estado |
|---|---|---|---|---|
| raw_ohlcv_1m/5m/15m | upsert | ingestion.py | ts,ticker,symbol_id,open,high,low,close,volume | ✅ OK |
| raw_ohlcv_rt | upsert | alpaca_prices.py | ticker,timeframe,ts,open,high,low,close,volume,fetched_at | ✅ OK |
| raw_news_alpaca | upsert | news_alpaca.py | published_at,title,summary,url,source,ticker,category | ✅ OK |
| raw_news_rt | upsert | alpaca_news.py | ticker,published_at,title,summary,url,source,fetched_at | ✅ OK |
| silver_news_alpaca | upsert | finbert.py | published_at,title,summary,url,source,ticker,category,sentiment_label,sentiment_score | ✅ OK |
| silver_features_1m/5m/15m | upsert | silver.py | 31 cols incluyendo news_count + sentiment_label_encoded | ⚠️ R-01: sentiment_label_encoded puede no existir. Falta `category`. |
| silver_features_rt | upsert | silver_rt.py | 31 cols con sentiment_label_encoded | ✅ OK (columna existe) |
| silver_predictions | upsert | evaluate.py | experiment_name,model_name,ticker,ts,y_true,y_pred,y_prob,confidence_low,confidence_high | ✅ OK |
| silver_metrics | upsert | evaluate.py | experiment_name,model_name,ticker,metric_name,metric_value | ✅ OK |
| silver_model_registry | insert | train.py | 18 campos incluyendo ticker y file_path relativo | ✅ OK |
| silver_model_registry | update | evaluate.py | metrics_summary (merge), status='complete' | ✅ OK |
| silver_model_registry | update | train.py | is_active=False (desactivar anteriores) | ✅ OK |
| gold_signals | upsert | db.py | ts,ticker,experiment_name,model_name,y_pred,y_prob,score,run_at | ✅ OK |
| gold_decisions | upsert | db.py | ts,ticker,decision,score_final,detalle_modelos,ejecutada,motivo_rechazo,run_at | ✅ OK |
| gold_trades | insert | alpaca_trader.py | 15 campos (todos incluidos, algunos NULL inicial) | ✅ OK |
| gold_trades | update | reconciliation.py | status,precio_entrada,ts_salida,precio_salida,pnl,pnl_pct,motivo_salida | ✅ OK |
| gold_trades | update | alpaca_trader.py (close_all) | ts_salida,motivo_salida,status | ⚠️ I-03: falta precio_salida, pnl, pnl_pct |
| gold_logs | insert | db.py | run_at,run_id,duration_s,tickers_procesados,senales_generadas,ordenes_ejecutadas,errores,status | ⚠️ I-06: run_id puede no existir |
| gold_pipeline_timings | insert | db.py | run_at,run_id,fase,duration_s,ticker,status | ✅ OK |
| config | select | guardrails.py | trading_enabled WHERE id=1 | ⚠️ Tabla puede no existir |
| ingestion_log | insert | ingestion.py | run_at,ticker,interval,start,end,inserted,skipped,status,error,duration_s | ⚠️ I-07: nombre de tabla a verificar |
| backtest_runs | insert | backtest.py | name,tickers,test_start,test_end,modelos,guardrails,capital_inicial | ✅ OK |
| backtest_trades | insert | backtest.py | backtest_name + 12 campos | ✅ OK |
| backtest_metrics | insert | backtest.py | backtest_name + 10 campos | ✅ OK |
| symbols | select | ingestion.py | id WHERE ticker=X | ✅ OK (solo lectura) |
| silver_model_library | select | registry.py | model_name,model_type,active,default_params | ✅ OK (solo lectura) |

---

## 5. ACCIONES INMEDIATAS REQUERIDAS

Antes de usar el ZIP entregado:

1. **Ejecutar en Supabase** el `scripts/schema_fixes.sql` tal como está
2. **Añadir a schema_fixes.sql** y ejecutar:
```sql
-- R-01: añadir sentiment_label_encoded a tablas históricas
ALTER TABLE silver_features_1m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
ALTER TABLE silver_features_5m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
ALTER TABLE silver_features_15m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
```
3. **Verificar nombre de tabla**: ejecutar `SELECT table_name FROM information_schema.tables WHERE table_name IN ('ingestion_log', 'ingestion_logs')` y alinear el código si es necesario
4. **Verificar que `gold_logs` tiene columna `run_id`** (el SQL lo crea si falta)
5. **Verificar que tabla `config` se creó** con `SELECT * FROM config`

---

*Fin del informe de re-auditoría — 26 abril 2026*
