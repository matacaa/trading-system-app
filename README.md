# Squawks ML — Trading System App

Plataforma de alertas de trading impulsadas por Machine Learning.

## Estructura del proyecto

```
trading-system-app/
│
├── apps/                          ← CÓDIGO ORIGINAL (funcional, sin cambios)
│   ├── api/main.py                   API FastAPI original (referencia)
│   ├── trading_engine/               Pipeline live original
│   ├── ingestion_live/               Ingesta de precios y noticias
│   ├── ingestion_historical/         Carga histórica de datos
│   ├── ml_sandbox/                   Training y backtest original
│   └── dashboard/                    Dashboard Grafana
│
├── services/                      ← MICROSERVICIOS (nuevo)
│   ├── api/                          API Gateway (FastAPI + routers)
│   │   ├── main.py                      Punto de entrada, solo routing
│   │   └── routers/                     Un archivo por dominio
│   │       ├── health.py
│   │       ├── tickers.py
│   │       ├── models.py                  Incluye /models/available (autodescubrimiento)
│   │       ├── training.py
│   │       ├── backtest.py
│   │       ├── live.py
│   │       ├── trading.py
│   │       ├── signals.py
│   │       └── squawks.py                 TODO fase 3
│   ├── ingestion/main.py            Servicio de ingesta (compartido)
│   ├── features/main.py             Feature engine + FinBERT (compartido)
│   ├── inference/main.py            Modelos ML × N usuarios (carril 1)
│   ├── decision/main.py             Guardrails × N usuarios (carril 1)
│   └── squawk/main.py               Alertas + TTS + push (carril 1)
│
├── workers/                       ← WORKERS ASYNC (nuevo)
│   ├── backtest/main.py              Jobs de backtest (carril 2)
│   └── training/main.py             Jobs de training GPU (carril 3)
│
├── shared/                        ← CÓDIGO COMPARTIDO (refactorizado)
│   ├── models/                       Modelos ML con autodescubrimiento
│   │   ├── base.py                      BaseModel con name, model_type, requires_gpu
│   │   ├── registry.py                  @register_model + auto-discover
│   │   ├── sklearn_models/
│   │   │   ├── xgboost_model.py         @register_model
│   │   │   ├── random_forest_model.py   @register_model
│   │   │   └── lightgbm_model.py        @register_model
│   │   └── pytorch_models/
│   │       ├── lstm_model.py            @register_model
│   │       ├── gru_model.py             @register_model
│   │       ├── transformer_model.py     @register_model
│   │       └── dataset.py
│   ├── signals/                      Fuentes de señales (nuevo)
│   │   ├── base.py                      BaseSignalSource + @register_signal
│   │   └── rules/                       Reglas técnicas plug-and-play
│   │       ├── golden_cross.py          SMA20 > SMA50
│   │       ├── rsi_oversold.py          RSI < umbral
│   │       ├── volume_spike.py          Volumen > Nx media
│   │       └── price_spike.py           Movimiento > X%
│   ├── inference.py                  Predicción unificada (usa registry)
│   ├── guardrails.py                 14 guardrails configurables
│   ├── indicators.py                 12 indicadores técnicos
│   ├── db.py                         Conexión Supabase/PostgreSQL
│   ├── config.py                     Configuración del sistema
│   └── symbols.py                    Lista de tickers
│
├── config/                        ← CONFIGURACIÓN
│   ├── live/                         Config del pipeline live
│   ├── backtests/                    Configs de backtests
│   └── experiments/                  Configs de training
│
├── tests/                         ← TESTS
├── scripts/                       ← SCRIPTS DE MANTENIMIENTO
├── data/                          ← DATOS LOCALES
├── requirements.txt
└── pyproject.toml
```

## Cómo funciona

### Ahora mismo (funcional)
El código en `apps/` funciona exactamente igual que antes.
Para ejecutar el sistema actual:

```bash
# API (puerto 8000)
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

# Pipeline live
python -m apps.trading_engine.main
```

### Nueva API con routers (funcional)
La API en `services/api/` tiene los mismos endpoints separados en archivos:

```bash
# Nueva API con routers (mismo puerto 8000)
python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Microservicios independientes (en progreso)
Los servicios en `services/` y `workers/` están preparados para ejecutarse
por separado cuando se migre a Azure Container Apps:

```bash
# Ingesta independiente
python -m services.ingestion.main

# Feature engine independiente
python -m services.features.main
```

## Añadir un modelo nuevo

1. Crea un archivo (ej: `shared/models/sklearn_models/catboost_model.py`)
2. Hereda de `BaseModel` y añade `@register_model`:

```python
from shared.models.base import BaseModel
from shared.models.registry import register_model

@register_model
class CatBoostModel(BaseModel):
    name = "catboost"
    model_type = "tree"
    requires_gpu = False

    def fit(self, X_train, y_train): ...
    def predict(self, X): ...
    def predict_proba(self, X): ...
    def save(self, path): ...
    @classmethod
    def load(cls, path, task="classification"): ...
```

3. El modelo aparece automáticamente en `GET /api/models/available`

## Añadir una regla técnica nueva

1. Crea un archivo (ej: `shared/signals/rules/macd_cross.py`)
2. Hereda de `BaseSignalSource` y añade `@register_signal`:

```python
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class MACDCross(BaseSignalSource):
    name = "macd_cross"
    source_type = "rule"
    requires_training = False
    description = "MACD cruza la línea de señal"

    def evaluate(self, features, config=None):
        macd = features.get("macd_line", 0)
        signal = features.get("macd_signal", 0)
        crossed = macd > signal
        return Signal(
            triggered=crossed,
            score=0.7 if crossed else 0.0,
            text=f"MACD cross: {macd:.4f} > signal {signal:.4f}",
            source_name=self.name,
            source_type=self.source_type,
        )
```

3. La regla aparece automáticamente en `list_signals()`

## Roadmap de migración

| Fase | Qué | Estado |
|------|-----|--------|
| 1 | Registry autodescubrible | ✅ Hecho |
| 1 | API separada en routers | ✅ Hecho |
| 1 | Signal sources (reglas técnicas) | ✅ Hecho |
| 2 | Dockerizar + Azure base | ⬜ Pendiente |
| 2 | Migrar PostgreSQL a Azure | ⬜ Pendiente |
| 3 | Auth + multi-tenant | ⬜ Pendiente |
| 3 | Squawk engine + TTS + push | ⬜ Pendiente |
| 4 | Service Bus + colas | ⬜ Pendiente |
| 4 | Cacheo inteligente (Redis) | ⬜ Pendiente |
| 5 | App móvil React Native | ⬜ Pendiente |
