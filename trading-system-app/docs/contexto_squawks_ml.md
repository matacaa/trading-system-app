# CONTEXTO PARA NUEVO CHAT — Squawks ML App

## Proyecto

Squawks ML es una app móvil de alertas de trading impulsadas por Machine Learning.
Los usuarios configuran modelos ML + reglas técnicas + guardrails, y reciben alertas personalizadas con audio cuando se cumplen sus condiciones.

- **Repo:** https://github.com/matacaa/trading-system-app
- **Path local:** C:\Users\jgrma\Desktop\APIs\trading-system-app
- **Stack:** Python 3.11, FastAPI, Supabase (PostgreSQL), Alpaca API, PyTorch, sklearn
- **Frontend futuro:** React Native + Expo (iOS + Android)
- **Cloud futuro:** Microsoft Azure

## Repo original

El proyecto se construyó sobre un sistema de trading algorítmico previo:
- **Repo original:** https://github.com/Matacaa7/trading-system
- **Frontend original:** https://github.com/Matacaa7/trading-frontend (Next.js 14)

## Qué está HECHO y TESTEADO (13/13 servicios ✅)

### Servicios probados manualmente:

| # | Servicio | Archivo | Comando | Estado |
|---|---|---|---|---|
| 1 | Ingestion RT | services/ingestion/main.py | `python -m services.ingestion.main --once` | ✅ |
| 2 | Ingestion histórica | apps/ingestion_historical/main.py | `python -m apps.ingestion_historical.main --tickers AAPL` | ✅ |
| 3 | Features RT | services/features/main.py | `python -m services.features.main --once` | ✅ |
| 4 | Features históricos | apps/ingestion_historical/silver.py | `python -m apps.ingestion_historical.main --only-silver` | ✅ |
| 5 | Model Registry | shared/models/registry.py | Auto-descubre 6 modelos con @register_model | ✅ |
| 6 | Signal Sources | shared/signals/rules/*.py | Auto-descubre 25 reglas con @register_signal | ✅ |
| 7 | Guardrails | shared/guardrails.py | 14 filtros de seguridad | ✅ |
| 8 | Inference | shared/inference.py | 6 modelos cargados + predicción real AAPL | ✅ |
| 9 | API Gateway | services/api/main.py + routers/ | 9 routers, 24 endpoints, todos respondiendo | ✅ |
| 10 | Squawk | services/squawk/main.py | Genera texto + prioridad | ✅ |
| 11 | Training | apps/ml_sandbox/pipeline.py | XGBoost entrenado: acc=66.4%, AUC=72.5% | ✅ |
| 12 | Backtest | apps/ml_sandbox/backtest.py | 810 velas, 2 trades, 100% win rate | ✅ |
| 13 | Pipeline live | apps/trading_engine/main.py | Ciclo completo: 7 señales, HOLD (mercado cerrado) | ✅ |

### Test suite automatizado: 27/27 tests pasando
```
python tests/test_all_services.py
```

## Estructura del proyecto

```
trading-system-app/
│
├── apps/                          ← CÓDIGO ORIGINAL (funcional)
│   ├── api/main.py                   API monolítica original (referencia)
│   ├── trading_engine/main.py        Pipeline live (loop cada 1 min)
│   ├── ingestion_live/               Ingesta RT (Alpaca)
│   │   ├── alpaca_prices.py             Descarga velas → raw_ohlcv_rt
│   │   ├── alpaca_news.py               Descarga noticias → raw_news_rt (ARREGLADO: NewsSet + dedup)
│   │   ├── finbert_rt.py                Sentimiento FinBERT
│   │   └── silver_rt.py                 Indicadores técnicos → silver_features_rt
│   ├── ingestion_historical/         Ingesta batch (Yahoo Finance + Alpaca News)
│   └── ml_sandbox/                   Training + Backtest
│       ├── pipeline.py                  Entrena modelos (--config yaml)
│       └── backtest.py                  Simula trades (--config yaml)
│
├── services/                      ← MICROSERVICIOS (nuevo, testeado)
│   ├── api/                          API Gateway con routers
│   │   ├── main.py                      FastAPI + 9 routers
│   │   └── routers/
│   │       ├── health.py                /api/health
│   │       ├── tickers.py               /api/tickers, /api/candles, /api/candles/historical
│   │       ├── models.py                /api/models, /api/models/available (autodescubrimiento)
│   │       ├── training.py              POST /api/train
│   │       ├── backtest.py              POST /api/backtest, GET /api/backtest/list
│   │       ├── live.py                  /api/live/status, /api/live/config
│   │       ├── trading.py              /api/trading/status, /api/trading/toggle, /api/portfolio
│   │       ├── signals.py              /api/signals/latest, /api/decisions/today, /api/trades
│   │       └── squawks.py              /api/squawks (placeholder)
│   ├── ingestion/main.py            Ingesta RT standalone
│   ├── features/main.py             Features RT standalone
│   ├── inference/main.py             Inference por usuario (preparado, no migrado)
│   ├── decision/main.py              Guardrails por usuario (preparado, no migrado)
│   └── squawk/main.py                Generación texto + prioridad (TODO: TTS + push)
│
├── workers/                       ← WORKERS ASYNC (estructura, no migrado)
│   ├── backtest/main.py              Jobs de backtest (TODO: Service Bus + cacheo)
│   └── training/main.py             Jobs de training (TODO: Service Bus + GPU)
│
├── shared/                        ← CÓDIGO COMPARTIDO (refactorizado)
│   ├── models/                       6 modelos ML con autodescubrimiento
│   │   ├── base.py                      BaseModel con name, model_type, requires_gpu
│   │   ├── registry.py                  @register_model + _auto_discover() + load_model_from_path()
│   │   ├── sklearn_models/              XGBoost, RandomForest, LightGBM (@register_model)
│   │   └── pytorch_models/              LSTM, GRU, Transformer (@register_model)
│   ├── signals/                      25 reglas técnicas con autodescubrimiento
│   │   ├── base.py                      BaseSignalSource + Signal + @register_signal (acepta df_hist)
│   │   └── rules/                       25 archivos, cada uno una regla configurable
│   │       ├── Cruces: golden_cross, death_cross, ema_bounce, ema_break, triple_ema_align
│   │       ├── Osciladores: rsi_oversold, rsi_overbought, rsi_divergence, macd_cross_up/down, macd_zero_cross
│   │       ├── Volatilidad: bollinger_squeeze, bollinger_touch_lower/upper, atr_expansion, atr_contraction
│   │       ├── Volumen/Precio: volume_spike, volume_dry_up, price_spike, vwap_cross_up/down
│   │       └── Sentimiento: sentiment_extreme_positive/negative, sentiment_flip, news_volume_spike
│   ├── inference.py                  Predicción unificada (usa registry, sin if/elif hardcodeado)
│   ├── guardrails.py                 14 guardrails configurables
│   ├── indicators.py                 12 indicadores técnicos
│   ├── db.py                         Conexión Supabase
│   ├── config.py                     Lee .env (Supabase, Alpaca, HuggingFace)
│   └── symbols.py                    16 tickers
│
├── config/                        ← CONFIGURACIÓN
│   ├── live/ensemble.yaml            Config del pipeline live
│   ├── experiments/*.yaml            Configs de training (6 modelos)
│   └── backtests/*.yaml              Configs de backtest
│
├── tests/
│   ├── test_all_services.py          27 tests automatizados (todos pasan)
│   └── MANUAL_TESTING.md             Guía de testing manual servicio por servicio
│
├── data/models/                   ← Modelos entrenados (.pkl, .pt)
├── .env                           ← Credenciales (Supabase, Alpaca, HuggingFace)
└── requirements.txt
```

## Supabase — Tablas (arquitectura Medallion)

### RAW (datos crudos)
- raw_ohlcv_1m/5m/15m — Velas históricas (Yahoo Finance)
- raw_ohlcv_rt — Velas en tiempo real (Alpaca)
- raw_news_alpaca — Noticias históricas
- raw_news_rt — Noticias en tiempo real

### SILVER (procesados)
- silver_features_1m/5m/15m — Indicadores técnicos históricos
- silver_features_rt — Indicadores técnicos en tiempo real
- silver_news_alpaca — Noticias con sentimiento FinBERT
- silver_model_registry — Modelos entrenados registrados
- silver_model_library — Catálogo de tipos de modelo con params por defecto

### GOLD (resultados)
- gold_signals — Señales de los modelos ML
- gold_decisions — Decisiones BUY/HOLD con motivo
- gold_trades — Operaciones ejecutadas en Alpaca
- gold_logs — Logs del pipeline
- gold_pipeline_timings — Tiempos de cada paso

### BACKTEST
- backtest_runs — Configuración y resultados de backtests
- backtest_trades — Trades simulados
- backtest_metrics — Métricas de rendimiento

### SYSTEM
- config — trading_enabled, circuit_breaker

## Modelos ML entrenados (AAPL 1m)

| Modelo | Accuracy | F1 | AUC | Tipo |
|---|---|---|---|---|
| XGBoost | 66.4% | 0.677 | 0.725 | tree (CPU) |
| Random Forest | 64.4% | 0.641 | 0.704 | tree (CPU) |
| LightGBM | 66.4% | 0.684 | 0.724 | tree (CPU) |
| LSTM | 78.7% | 0.763 | 0.908 | deep_learning (GPU) |
| GRU | 89.0% | 0.896 | 0.966 | deep_learning (GPU) |
| Transformer | 78.2% | 0.814 | 0.914 | deep_learning (GPU) |

## Bugs arreglados en este chat

1. ✅ alpaca_news.py — NewsSet de alpaca-py no tiene .news, usa dict(response)["data"]["news"]
2. ✅ alpaca_news.py — articles son objetos News (article.headline), no dicts (article.get())
3. ✅ alpaca_news.py — URLs duplicadas en upsert: dedup antes de guardar
4. ✅ Signal rules — numpy.bool_ vs bool: añadir bool() en cada comparación
5. ✅ Dependencias faltantes: apscheduler, exchange_calendars, yfinance, fastapi, alpaca-py

## Extensibilidad

### Añadir modelo nuevo:
1. Crear shared/models/sklearn_models/nuevo_modelo.py (o pytorch_models/)
2. Heredar de BaseModel, añadir @register_model, definir name/model_type/requires_gpu
3. Push a GitHub → aparece automáticamente en /api/models/available

### Añadir regla técnica nueva:
1. Crear shared/signals/rules/nueva_regla.py
2. Heredar de BaseSignalSource, añadir @register_signal
3. Implementar evaluate(features, config, df_hist) → Signal
4. Push → aparece automáticamente en list_signals()

### Parámetros configurables por regla:
- Cada regla recibe config dict con umbrales del usuario
- Valores por defecto si el usuario no configura nada
- El frontend mostrará cada regla como toggle + sliders

## Arquitectura target (Azure)

### 3 carriles de cómputo:
1. **Live (always-on):** Ingestion → Features → Inference × N usuarios → Decision → Squawk
2. **Backtest (elástico):** Cola Service Bus → Cache check Redis → Inference o replay → Resultados
3. **Training (GPU async):** Cola Service Bus → Azure ML Compute → Blob Storage → Invalidar cache

### Servicios Azure planificados:
- Azure Container Apps — API + servicios live
- Azure Container Apps Jobs — Backtests
- Azure ML Compute — Training GPU
- Azure Database for PostgreSQL Flexible Server — Reemplaza Supabase
- Azure Cache for Redis — Cacheo de backtests + rate limiting
- Azure Blob Storage + CDN — Modelos + audios
- Azure SignalR Service — Feed en tiempo real
- Azure Notification Hubs — Push notifications iOS/Android
- Azure Speech Services — TTS para squawks (reemplaza ElevenLabs)
- Azure Service Bus — Colas de backtest y training

## Documentos generados

1. **Squawks_ML_Arquitectura_Tecnica.docx** — Arquitectura completa, servicios Azure, DB, seguridad, planes, P&L, roadmap
2. **Squawks_ML_Lineas_de_Trabajo.docx** — 7 líneas: desarrollo, legal, marketing, marca, finanzas, soporte, producto

## ROADMAP — PASOS SIGUIENTES DETALLADOS

### FASE 2: Dockerizar (2 semanas)

**Paso 2.1 — Crear Dockerfiles (3h)**
- Dockerfile.api para services/api/ (FastAPI + uvicorn)
- Dockerfile.ingestion para services/ingestion/ (scheduler)
- Dockerfile.features para services/features/ (FinBERT pesado, ~2GB imagen)
- Dockerfile.engine para apps/trading_engine/ (pipeline live)
- Cada Dockerfile: FROM python:3.11-slim, COPY requirements, COPY código, CMD
- Base image compartida con dependencias comunes (torch, sklearn, etc.)

**Paso 2.2 — docker-compose.dev.yml (2h)**
- Definir todos los servicios con volúmenes para desarrollo local
- API en puerto 8000, con hot-reload via volume mounts
- Variables de entorno desde .env
- Red interna entre servicios

**Paso 2.3 — Probar en local con Docker (4h)**
- docker-compose up → verificar que todos los servicios arrancan
- Probar los mismos 13 tests pero dentro de contenedores
- Verificar que la API responde, que la ingesta funciona, que la inference predice

**Paso 2.4 — CI/CD con GitHub Actions (3h)**
- .github/workflows/deploy.yml
- On push to main: build images → push a Azure Container Registry
- Tests automatizados antes de deploy

### FASE 3: Azure base (2 semanas)

**Paso 3.1 — Crear cuenta Azure + Resource Group (1h)**
- Registrar cuenta Azure (free tier tiene 200$ crédito)
- Crear Resource Group "squawks-ml"
- Instalar Azure CLI

**Paso 3.2 — Azure Container Registry (1h)**
- Crear ACR (Basic tier, ~5€/mes)
- Configurar GitHub Actions para push automático
- docker push a ACR desde CI/CD

**Paso 3.3 — Azure PostgreSQL Flexible Server (2h)**
- Provisionar B1ms (1 vCPU, 2GB, ~15€/mes)
- Migrar datos: pg_dump de Supabase → pg_restore en Azure
- Actualizar connection string en .env / config
- Verificar las 25+ tablas

**Paso 3.4 — Deploy Container Apps (3h)**
- Crear Container Apps Environment
- Deploy API como Container App (port 8000, ingress external)
- Deploy trading engine como Container App (worker, always-on)
- Variables de entorno desde Azure Key Vault

**Paso 3.5 — Verificar todo en Azure (4h)**
- API responde desde URL pública de Azure
- Pipeline live corre en Azure 24/7
- Ingesta funciona contra Alpaca desde Azure
- Comparar resultados con versión local

### FASE 4: Auth + multi-tenant (2 semanas)

**Paso 4.1 — Tablas de usuarios (2h)**
- CREATE TABLE users (id, email, password_hash, plan, trial_end, created_at)
- CREATE TABLE subscriptions (user_id, plan, stripe_id, started_at, expires_at)
- CREATE TABLE user_preferences (user_id, tickers, signal_configs, notification_prefs)

**Paso 4.2 — Auth en FastAPI (6h)**
- POST /auth/register — crear usuario con bcrypt hash
- POST /auth/login — verificar password, devolver JWT
- POST /auth/refresh — renovar access token con refresh token
- Middleware que verifica JWT en cada request
- Dependencia get_current_user() en cada router

**Paso 4.3 — user_id en tablas personalizadas (8h)**
- ALTER TABLE en gold_signals, gold_decisions, backtest_runs, etc.
- Añadir índices por user_id
- Actualizar TODAS las queries para filtrar por user_id

**Paso 4.4 — Rate limiting con Redis (4h)**
- Provisionar Azure Cache for Redis (Basic, ~15€/mes)
- Contar backtests/trainings por user_id por día
- Responder 429 si excede límite del plan

### FASE 5: Squawk engine completo (2 semanas)

**Paso 5.1 — Tabla gold_squawks (1h)**
- id, user_id, ticker, signal_type, score, text, audio_url, priority, delivered_via, created_at

**Paso 5.2 — Integrar señales en pipeline (4h)**
- Después de la inference ML, evaluar las 25 reglas técnicas del usuario
- Combinar señales ML + reglas → decidir si generar squawk
- Squawk engine genera texto personalizado

**Paso 5.3 — Azure Speech Services TTS (4h)**
- Texto del squawk → audio MP3
- Subir MP3 a Blob Storage con CDN
- Guardar URL en gold_squawks.audio_url

**Paso 5.4 — SignalR para feed en tiempo real (4h)**
- Provisionar Azure SignalR Service
- Hub "squawks" que envía alertas a usuarios conectados
- La app móvil se conecta y recibe squawks al instante

**Paso 5.5 — Notification Hubs para push (4h)**
- Provisionar Azure Notification Hubs
- Configurar APNs (iOS) + FCM (Android)
- Alertas urgentes (score >90%) → push notification

### FASE 6: Colas de backtest + training (2 semanas)

**Paso 6.1 — Azure Service Bus (2h)**
- Crear namespace + backtest-queue + training-queue
- Prioridad por plan (Pro > Premium > Trial)

**Paso 6.2 — Cacheo inteligente en Redis (8h)**
- Cache key = hash(model_id + ticker + window)
- Si solo cambiaron guardrails → replay desde cache (~200ms vs ~30s)
- Invalidar cache cuando se re-entrena un modelo

**Paso 6.3 — Container Apps Jobs para backtests (4h)**
- Job que lee de backtest-queue
- Autoscale 0→10 según cola

**Paso 6.4 — Azure ML Compute para training (4h)**
- GPU cluster T4, escala 0→3 nodos
- Training jobs como Azure ML Jobs

### FASE 7: Pagos + suscripciones (2 semanas)

**Paso 7.1 — Cuentas Apple Developer + Google Play (2h)**
**Paso 7.2 — Productos in-app: Premium 15€/mes, Pro 40€/mes (3h)**
**Paso 7.3 — RevenueCat para unificar iOS + Android + Web (3h)**
**Paso 7.4 — Stripe para pagos web (4h)**
**Paso 7.5 — Webhook handler en FastAPI (6h)**

### FASE 8: App móvil React Native (3-4 semanas)

**Paso 8.1 — Crear proyecto Expo + estructura (3h)**
**Paso 8.2 — Pantallas auth (login, registro) (8h)**
**Paso 8.3 — Feed de squawks (timeline + audio) (12h)**
**Paso 8.4 — Push notifications (6h)**
**Paso 8.5 — Configuración (tickers, modelos, guardrails, reglas) (10h)**
**Paso 8.6 — Backtest (lanzar, ver resultados) (12h)**
**Paso 8.7 — Training (lanzar, ver métricas) (8h)**
**Paso 8.8 — Perfil + suscripción (RevenueCat) (8h)**
**Paso 8.9 — Diseño UI + polish + onboarding (10h)**

### FASE 9: Testing + lanzamiento (2 semanas)

**Paso 9.1 — Build TestFlight + Internal Testing (4h)**
**Paso 9.2 — Beta con 10-20 testers (8h + 12h bugs)**
**Paso 9.3 — Disclaimers + Privacy Policy + ToS (7h)**
**Paso 9.4 — App Store assets (screenshots, descripción) (6h)**
**Paso 9.5 — Submit a Apple + Google (4h)**
**Paso 9.6 — Lanzamiento coordinado con Trading Pills (4h)**

## Planes de suscripción

| Límite | Trial (14 días) | Premium (15€/mes) | Pro (40€/mes) |
|---|---|---|---|
| Backtests/día | 3 | 30 | Ilimitado |
| Ventana backtest | 1 semana | 1 mes | 3 meses |
| Trainings/semana | 1 | 5 | Ilimitado |
| Tickers | 1 (AAPL) | 5 | 16+ |
| Modelos | 3 (tree) | 6 (todos) | 6 + pesos custom |
| Reglas técnicas | 5 | 15 | 25 (todas) |
| Alertas | Solo texto | Texto + audio | Texto + audio + prioridad |

## Proyección financiera

| | 10 users | 100 users | 1.000 users | 10.000 users |
|---|---|---|---|---|
| Ingreso neto | 100€ | 1.180€ | 13.400€ | 146.000€ |
| Coste total | 133€ | 285€ | 2.550€ | 19.000€ |
| P&L mensual | -33€ | +895€ | +10.850€ | +127.000€ |
| Margen | -33% | 76% | 81% | 87% |

Breakeven: ~30 usuarios de pago.

## Líneas de trabajo paralelas (no técnicas)

- **Legal:** Consulta abogado fintech CNMV, forma jurídica (autónomo/SL), GDPR, ToS
- **Marketing:** Trading Pills como funnel, teasers, lista de espera, lanzamiento coordinado
- **Marca:** Naming, dominio, logo, paleta, cuentas de redes
- **Finanzas:** Alta fiscal, gestoría, control costes Azure
- **Soporte:** FAQ, onboarding, canal soporte, comunidad Discord
- **Producto:** KPIs, feedback loops, validación pricing

## Notas técnicas importantes

- **Yahoo Finance** limita datos 1m a 8 días máximo
- **FinBERT** tarda ~100s en cargar la primera vez en CPU, luego queda en memoria
- **alpaca-py** versión actual: NewsSet se itera como dict, articles son objetos News (no dicts)
- **exchange_calendars** necesario para is_market_open en indicadores
- **Modelos .pkl/.pt** están en data/models/ — copiar desde trading-system si faltan
- **PowerShell** necesita -UseBasicParsing para Invoke-WebRequest
