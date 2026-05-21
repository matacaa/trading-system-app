# trading-system

Sistema de trading algorítmico intraday con ML sobre equities US. Ensemble de 6 modelos (XGBoost, Random Forest, LightGBM, LSTM, GRU, Transformer) operando con velas de 1 minuto en paper trading con Alpaca.

## Arquitectura

```
                    ┌─────────────────────────────┐
                    │     Frontend (Next.js)       │
                    │     localhost:3001            │
                    └──────────┬──────────────────┘
                               │ HTTP
                    ┌──────────▼──────────────────┐
                    │     FastAPI :8000             │
                    │     apps/api/main.py          │
                    └──────────┬──────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
    ┌─────▼─────┐     ┌───────▼───────┐     ┌──────▼──────┐
    │  Training  │     │   Backtest    │     │  Live Engine │
    │ ml_sandbox │     │  ml_sandbox   │     │trading_engine│
    └─────┬─────┘     └───────┬───────┘     └──────┬──────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Supabase (PgSQL)  │
                    │  RAW → SILVER → GOLD │
                    └───────────────────┘
```

## Estructura del repo

```
trading-system/
├── shared/                         # Librería compartida
│   ├── db.py                       # Singleton Supabase client
│   ├── config.py                   # Configuración (.env + tabla config)
│   ├── indicators.py               # Fuente canónica de indicadores técnicos
│   ├── guardrails.py               # 14 guardrails configurables
│   ├── inference.py                # Carga modelos + predict_ensemble
│   ├── symbols.py                  # Universo de 16 tickers
│   ├── models/
│   │   ├── base.py                 # Clase abstracta BaseModel
│   │   ├── registry.py             # Mapeo nombre → clase
│   │   ├── sklearn_models/         # XGBoost, Random Forest, LightGBM
│   │   └── pytorch_models/         # LSTM, GRU, Transformer + dataset.py
│   └── utils/                      # logging, time
├── apps/
│   ├── api/main.py                 # FastAPI — bridge frontend↔backend
│   ├── ingestion_historical/       # Pipeline batch: yfinance + Alpaca News + FinBERT + Silver + Tensors
│   ├── ingestion_live/             # Pipeline RT cada minuto: precios + noticias + silver
│   ├── trading_engine/             # Loop principal: predict → decide → execute → reconcile
│   ├── ml_sandbox/                 # Training + evaluación + backtest
│   └── dashboard/                  # Placeholder (Grafana usado en su lugar)
├── config/
│   ├── experiments/                # YAMLs de entrenamiento (1 por modelo)
│   ├── backtests/                  # YAMLs de backtests
│   └── live/
│       ├── ensemble.yaml           # Config activa del ensemble (modelos + pesos + guardrails)
│       └── trading.yaml            # Config del pipeline (intervalo, timeframe)
├── data/
│   ├── models/                     # .pkl (sklearn) y .pt (PyTorch) guardados
│   └── tensors/                    # .npy para cada timeframe
├── scripts/
│   ├── verify_system.py            # 24 checks pre-arranque
│   ├── schema_fixes.sql            # SQL para Supabase
│   └── post_fix_audit.md           # Auditoría de integridad
└── tests/                          # pytest (indicadores, modelos, paridad)
```

## Supabase — 25 tablas (Arquitectura Medallion)

| Capa | Tablas |
|---|---|
| RAW | raw_ohlcv_1m, raw_ohlcv_5m, raw_ohlcv_15m, raw_ohlcv_rt, raw_news_alpaca, raw_news_rt |
| SILVER | silver_features_1m/5m/15m, silver_features_rt, silver_news_alpaca, silver_model_registry, silver_predictions, silver_metrics, silver_model_library |
| GOLD | gold_signals, gold_decisions, gold_trades, gold_logs, gold_pipeline_timings |
| BACKTEST | backtest_runs, backtest_trades, backtest_metrics |
| SYSTEM | config, symbols, ingestion_log |

## Setup

```bash
# 1. Clonar
git clone https://github.com/Matacaa7/trading-system.git
cd trading-system

# 2. Crear venv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# 3. Instalar
pip install -e .

# 4. Configurar credenciales
copy .env.example .env
# Editar .env con claves de Supabase, Alpaca, HuggingFace

# 5. Preparar Supabase
# Ejecutar scripts/schema_fixes.sql en Supabase SQL Editor
# Ejecutar SQL de inserción de los 16 symbols

# 6. Verificar
python scripts/verify_system.py
```

## Pipeline paso a paso

### 1. Ingesta histórica
```bash
# Todo (RAW + FinBERT + Silver + Tensors) — 16 tickers, ~20 min
python -m apps.ingestion_historical.main

# Solo una fase
python -m apps.ingestion_historical.main --only-silver
python -m apps.ingestion_historical.main --only-finbert
python -m apps.ingestion_historical.main --only-tensors

# Tickers específicos
python -m apps.ingestion_historical.main --tickers AAPL MSFT
```

### 2. Entrenar modelos
```bash
# Desde YAML
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_xgboost_1m_v2.yaml

# Los 6 modelos
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_xgboost_1m_v2.yaml
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_rf_1m_v2.yaml
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_lgbm_1m_v2.yaml
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_lstm_1m_v2.yaml
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_gru_1m_v2.yaml
python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_transformer_1m_v2.yaml
```

### 3. Backtest
```bash
python -m apps.ml_sandbox.backtest --config config/backtests/aapl_backtest_v1.yaml
```

### 4. Trading en vivo
```bash
# Arrancar API (necesaria para el frontend)
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

# Arrancar pipeline live (en otra terminal)
python -m apps.trading_engine.main
```

## 6 modelos ML

| Modelo | Tipo | Accuracy | F1 | AUC | Tiempo |
|---|---|---|---|---|---|
| XGBoost | sklearn | 66.4% | 0.677 | 0.725 | 0.3s |
| Random Forest | sklearn | 64.4% | 0.641 | 0.704 | 0.6s |
| LightGBM | sklearn | 66.4% | 0.684 | 0.724 | 3.7s |
| LSTM | PyTorch | 78.7% | 0.763 | 0.908 | 14.6s |
| GRU | PyTorch | 89.0% | 0.896 | 0.966 | 14.7s |
| Transformer | PyTorch | 78.2% | 0.814 | 0.914 | 56.4s |

Entrenados con 1,181 barras de AAPL 1m (10-15 abril 2026), testeados con 390 barras (16-17 abril).

## 14 guardrails configurables

Todos se configuran en el YAML del ensemble y se aplican tanto en backtest como en live:

score_threshold, score_minimo, RSI sobrecompra/sobreventa, MACD tendencia, Bollinger techo, ATR volatilidad, Volumen mínimo, EMA tendencia, VWAP spread, Sentiment, Horario mercado, Posición abierta, Max posiciones, Órdenes diarias max, Circuit breaker.

## API FastAPI — endpoints

| Endpoint | Método | Descripción |
|---|---|---|
| /api/health | GET | Health check |
| /api/tickers | GET | 16 tickers del universo + has_data |
| /api/data-range | GET | Rango de fechas disponibles |
| /api/models | GET | Modelos activos (filtrable por ticker) |
| /api/models/all | GET | Todos los modelos |
| /api/train | POST | Entrena un modelo |
| /api/backtest | POST | Ejecuta un backtest |
| /api/backtest/list | GET | Lista backtests con config |
| /api/backtest/results/{name} | GET | Resultados de un backtest |
| /api/portfolio | GET | Estado del portfolio en Alpaca |
| /api/trading/status | GET | ¿Trading activado? |
| /api/trading/toggle | POST | Activar/desactivar ejecución de órdenes |
| /api/live/config | GET/POST | Leer/escribir ensemble.yaml |
| /api/live/start | POST | Arrancar pipeline live |
| /api/live/stop | POST | Parar pipeline live |
| /api/live/status | GET | Estado del pipeline + trading_enabled |
| /api/candles | GET | Velas RT recientes |
| /api/candles/historical | GET | Velas históricas de un día |
| /api/signals/latest | GET | Señales actuales del ensemble |
| /api/decisions/today | GET | Decisiones del día |
| /api/trades | GET | Trades recientes |

## Monitorización — Grafana

Grafana en localhost:3000 con conexión directa a Supabase PostgreSQL. Dashboards:

- **RAW**: OHLCV por ticker/timeframe, timeline, noticias, anotaciones
- **Silver**: indicadores técnicos, sentiment, news_count, NULLs
- **Models & Backtests**: registry, métricas comparativas, predicciones, historial
- **Real-time**: señales, decisiones, trades, pipeline logs, config

## Puertos

| Servicio | Puerto |
|---|---|
| FastAPI | 8000 |
| Next.js frontend | 3001 |
| Grafana | 3000 |
| Supabase | remoto (jujjjtddjflimnpfbdkz.supabase.co) |

## Licencia

MIT — Copyright 2026 Javier Garcia
