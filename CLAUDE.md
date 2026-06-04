# CLAUDE.md — Squawks ML

Reglas permanentes del proyecto. Léelas al inicio de cada sesión.

## Qué es

SaaS de alertas de trading ("squawks" de audio). Detecta oportunidades con ML + guardrails + señales técnicas. **Servicio informativo, NO ejecuta órdenes.** Slogan: "Stop trusting. Start testing."

## Plan vigente

**El plan de trabajo actual está en `docs/contexto-sesion-18-plan-definitivo.md`** (bugs, mejoras acordadas con decisiones de diseño cerradas, y sprints S0-S9). Antes de implementar nada, localiza la tarea en ese documento y respeta sus decisiones. Si crees que hay que desviarse del plan, dilo en la PR y NO lo implementes por tu cuenta.

## Stack y estructura

- **Backend:** FastAPI · Python 3.11 · psycopg2 directo contra PostgreSQL (Azure). **NO Supabase** (cualquier referencia a Supabase es legacy a eliminar).
- **Frontend:** `frontend/` — Next.js 16 App Router · Tailwind v4 · Zustand · Axios · Recharts. La pestaña Squawks es `frontend/src/app/dashboard/page.tsx`.
- **Engine live:** `apps/trading_engine/` (ciclo 1 min: guardrails PRE → inferencia → POST → squawk + TTS).
- **ML:** `apps/ml_sandbox/` (train, evaluate, backtest). Ingesta: `apps/ingestion_historical/`, `apps/ingestion_live/`.
- **API:** `services/api/` (16 routers). Común: `shared/` (db, inference, guardrails, blob_storage, squawk_generator).
- **Migraciones:** `scripts/*.sql`, ejecución manual ordenada por fase.
- Rama de trabajo: **`master`** (no main).

## Comandos

```bash
# Tests con DB local de la sesión (NUNCA contra Azure):
service postgresql start
# ejecutar scripts/*.sql en orden de fase contra la DB local
pytest

# Gates obligatorios antes de entregar (la PR no es válida si fallan):
ruff check .                  # cero errores
cd frontend && npx next build # cero errores TypeScript
```

## Convenciones y trampas conocidas

- `get_conn()` SIEMPRE como context manager (`with get_conn() as conn:`). Usarlo como conexión cruda crasheaa (bug latente en backtest.py, models.py, live.py — corrígelo si tocas esos ficheros).
- `gold_squawks` usa columnas `decision`, `motivo`, `is_starred`, `guardrails_passed`. NO existen `title`, `body`, `direction`, `is_favorite` — los fixes van en el ROUTER (aliases), nunca ALTER TABLE.
- Emails case-insensitive: `LOWER()` en lookups, normalización a minúsculas en registro.
- Orden del pipeline: **guardrails PRE primero, inferencia solo si pasan**, POST después. Cualquier código nuevo respeta este orden.
- Sidebar de training: una entrada por nombre de modelo (retrain sobrescribe, no duplica).
- Datos de prueba limitados: 11 tickers en silver_features; AAPL solo 10–24 abril 2026. Úsalo en tests.
- `workers/` (raíz) es un stub obsoleto de un diseño antiguo — no lo uses como referencia; el diseño vigente de workers está en el plan (mejora #1).
- Frontend en desarrollo local usa puerto **3001** (CORS configurado para ello).
- Español para docstrings, comentarios y mensajes de commit descriptivos.

## Lo que NUNCA debes hacer

- Conectarte a la base de datos de Azure ni pedir/usar credenciales reales. Las pruebas van contra el PostgreSQL local de la sesión.
- Commitear secretos, `.env`, API keys o tokens. `.env.example` solo con placeholders.
- Tocar Stripe en modo live, precios o `plan_config` sin que la tarea lo pida explícitamente.
- PRs gigantes multipropósito: una tarea del plan = una rama `feat/sX-descripcion` o `fix/...` = una PR pequeña con resumen de cambios e instrucciones de validación local.
- Mergear tú mismo: las PRs las valida y mergea Javier tras probar en local contra Azure.
