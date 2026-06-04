# Squawks ML

**SaaS de alertas de trading impulsadas por Machine Learning.** Squawks ML analiza equities US en tiempo real con un ensemble de modelos ML + reglas técnicas y, cuando se cumplen las condiciones que el usuario configura, genera **alertas (squawks)** con texto y audio. Es una app de **alertas, no de ejecución de órdenes**: el sistema detecta oportunidades y avisa; el usuario decide si opera por su cuenta.

- **Backend:** FastAPI + **Azure PostgreSQL** (Flexible Server) vía `psycopg2`.
- **Frontend:** Next.js 16 + React 19 (`frontend/`).
- **Cloud:** Microsoft Azure (Container Apps, PostgreSQL, Blob Storage, Speech, ACR).
- **Broker de datos:** Alpaca (paper) para precios y noticias.

> Estado: Fase 8 (frontend ~95%). Fases 1–7 cerradas (Azure, auth multi-tenant, squawk engine, colas, pagos Stripe).

---

## Arquitectura

```
            ┌───────────────────────────────┐
            │   Frontend — Next.js 16        │
            │   frontend/  (Vercel / :3000)  │
            └───────────────┬───────────────┘
                            │ HTTPS (JWT)
            ┌───────────────▼───────────────┐
            │   API Gateway — FastAPI :8000  │
            │   services/api/main.py         │
            │   auth · stripe · tickers ·    │
            │   models · training · backtest │
            │   · live · signals · squawks   │
            └───────────────┬───────────────┘
                            │
     ┌──────────────────────┼──────────────────────┐
     │                      │                       │
┌────▼─────┐        ┌───────▼───────┐       ┌──────▼───────┐
│ Ingestion │        │ Trading Engine │       │  ML Sandbox  │
│   live    │        │ (loop 1 min)   │       │ train + bt   │
│ apps/     │        │ apps/          │       │ apps/        │
└────┬─────┘        └───────┬───────┘       └──────┬───────┘
     │                      │                       │
     └──────────────────────┼───────────────────────┘
                            │
                ┌───────────▼────────────┐
                │  Azure PostgreSQL       │
                │  RAW → SILVER → GOLD    │
                └────────────────────────┘
                            │
          Azure Blob (modelos + audios) · Azure Speech (TTS)
```

### Carriles de cómputo (Azure)

1. **Live (always-on):** ingestion → features → inference → guardrails → squawk. Contenedores `api`, `engine`, `ingestion`.
2. **Backtest / Training (bajo demanda):** lanzados desde la API, con límites por plan.

---

## Estructura del repo

```
trading-system-app/
├── shared/                  # Librería compartida (importada por todo)
│   ├── db.py                #   Pool PostgreSQL (psycopg2) — query/execute/upsert
│   ├── config.py            #   Singleton de configuración (.env)
│   ├── indicators.py        #   Indicadores técnicos canónicos
│   ├── guardrails.py        #   Guardrails configurables (LONG/SHORT)
│   ├── inference.py         #   Carga de modelos + predict_ensemble
│   ├── signals/             #   25 reglas técnicas autodescubiertas
│   ├── models/              #   6 modelos ML (sklearn + pytorch)
│   ├── blob_storage.py      #   Azure Blob (modelos por usuario)
│   ├── tts.py               #   Azure Speech → audio de squawks
│   ├── stripe_service.py    #   Checkout, packs y webhooks de Stripe
│   ├── plan_limits.py       #   Límites por plan de suscripción
│   └── legacy_runners.py    #   Helpers de backtest/training vía subprocess
├── services/
│   ├── api/                 # API Gateway FastAPI (main.py + routers/ + auth/ + middleware/)
│   ├── ingestion/           # Ingesta RT standalone
│   ├── features/            # Feature engine standalone
│   ├── inference/           # (placeholder Fase futura)
│   ├── decision/            # (placeholder Fase futura)
│   └── squawk/              # Generación de texto + prioridad de squawks
├── apps/
│   ├── trading_engine/      # Pipeline live (loop cada 1 min)
│   ├── ingestion_live/      # Precios + noticias + FinBERT + silver RT
│   ├── ingestion_historical/# Pipeline batch (yfinance + Alpaca News + FinBERT)
│   └── ml_sandbox/          # Training + evaluación + backtest
├── frontend/                # Next.js 16 + React 19 (dashboard web)
├── config/                  # YAMLs: experiments, backtests, live (ensemble/trading)
├── docker/                  # Dockerfile.base/api/engine/ingestion
├── scripts/                 # Migraciones SQL + utilidades
├── tests/                   # pytest (indicadores, modelos, paridad)
└── docs/                    # Documentación y auditorías
```

---

## Stack y servicios

| Dominio | Tecnología |
|---|---|
| Base de datos | Azure Database for PostgreSQL Flexible Server (`psycopg2`, pool) |
| Auth | JWT (access + refresh), bcrypt, verificación por email (SMTP) |
| Pagos | Stripe (suscripciones + packs + webhooks) |
| Almacenamiento | Azure Blob Storage (modelos entrenados, audios) |
| Audio (TTS) | Azure Speech Services |
| ML tabular | scikit-learn, XGBoost, LightGBM |
| ML deep | PyTorch (LSTM, GRU, Transformer) |
| Sentimiento | FinBERT (`transformers`) |
| Mercado | Alpaca (precios + noticias), `exchange-calendars` |
| Scheduling | APScheduler |
| Cache (opcional) | Redis (`REDIS_URL`) — rate limiting |

### Modelos ML (ensemble)

6 modelos autodescubiertos vía `@register_model`: **XGBoost, Random Forest, LightGBM** (sklearn) y **LSTM, GRU, Transformer** (PyTorch). Operan sobre velas de 1 minuto con features técnicas + sentimiento. Añadir un modelo nuevo = crear el archivo en `shared/models/.../` con `@register_model`; aparece solo en la API.

### Señales técnicas

25 reglas configurables (`shared/signals/rules/`) autodescubiertas vía `@register_signal`: cruces, osciladores, volatilidad, volumen/precio y sentimiento. Cada regla recibe la config (umbrales) del usuario.

---

## Base de datos — arquitectura Medallion

| Capa | Contenido |
|---|---|
| **RAW** | OHLCV (1m/5m/15m/rt) y noticias crudas |
| **SILVER** | Features técnicas + sentimiento, registry de modelos, predicciones, métricas |
| **GOLD** | Señales, decisiones, trades, logs, timings, squawks |
| **BACKTEST** | Runs, trades y métricas de backtests |
| **SYSTEM / USERS** | config, symbols, users, subscriptions, preferences, guardrails por usuario, training_jobs |

Las migraciones SQL están en `scripts/migration_*.sql`.

---

## Setup local

```bash
# 1. Clonar
git clone https://github.com/matacaa/trading-system-app.git
cd trading-system-app

# 2. Entorno virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Instalar (fuente única de dependencias: pyproject.toml)
pip install -e ".[dev]"

# 4. Configurar credenciales
cp .env.example .env             # rellenar con valores reales (ver .env.example)

# 5. Arrancar la API
python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload

# 6. (otra terminal) Pipeline live
python -m apps.trading_engine.main
```

### Frontend

```bash
cd frontend
cp .env.example .env.local        # NEXT_PUBLIC_API_URL, Stripe publishable key
npm install
npm run dev                       # http://localhost:3000
```

### Docker (desarrollo)

```bash
# Construir la imagen base una vez
docker build -t squawks-base -f docker/Dockerfile.base .

# Levantar api + engine + ingestion
docker-compose -f docker-compose.dev.yml up --build
```

---

## Variables de entorno

Todas las variables que el código lee están documentadas en **`.env.example`**: PostgreSQL, Alpaca, HuggingFace, JWT, CORS, Azure Blob, Azure Speech, SMTP, Stripe y Redis. Copia ese archivo a `.env` y rellénalo.

---

## CI/CD

- **`.github/workflows/ci.yml`** — lint (`ruff`) + tests en cada push/PR a `master`.
- **`.github/workflows/deploy.yml`** — build & push de las 3 imágenes (`api`, `engine`, `ingestion`) a Azure Container Registry en `master`.

---

## Planes de suscripción

| Límite | Trial | Premium | Pro |
|---|---|---|---|
| Backtests / día | 3 | 30 | Ilimitado |
| Trainings / semana | 1 | 5 | Ilimitado |
| Tickers | 1 | 5 | 16+ |
| Modelos | 3 | 6 | 6 + pesos custom |
| Reglas técnicas | 5 | 15 | 25 |
| Alertas | Texto | Texto + audio | Texto + audio + prioridad |

---

## Licencia

MIT © 2026 Javier Garcia
