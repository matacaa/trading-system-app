# Auditoría de archivos — Squawks ML

> **Fecha:** 2026-06-04 · **Rama:** `audit/limpieza-raiz` · **Alcance:** archivos de la raíz + directorios sospechosos de residuo.
> **Estado del proyecto:** Fase 8 (frontend ~95%). Backend FastAPI + **Azure PostgreSQL** (ya **no** Supabase). Engine en `apps/trading_engine/`, ML en `apps/ml_sandbox/`, ingesta en `apps/ingestion_*`, frontend Next.js 16 en `frontend/`.
>
> ⚠️ **Este documento NO borra ni modifica nada.** Solo diagnostica. Los comandos de limpieza están al final para revisión manual.

## Leyenda de veredictos

| Veredicto | Significado |
|---|---|
| ✅ **VIGENTE** | Refleja el estado real del código. Mantener. |
| 🟡 **DESACTUALIZADO** | Sigue siendo útil pero contiene afirmaciones falsas. Corregir. |
| 🔴 **OBSOLETO-BORRAR** | Residuo sin valor actual. Eliminar. |
| 📦 **MOVER A docs/** | Contenido válido pero mal ubicado (ruido en la raíz). |

---

## 1. Tabla de veredictos

| Archivo / Directorio | Veredicto | Motivo | Acción propuesta |
|---|---|---|---|
| `README.md` | 🔴 OBSOLETO-BORRAR | No describe el proyecto: es el README de un **zip de fixes de la Fase 3c** ("Cómo usar este zip", "19 archivos a reemplazar", "3 archivos a borrar"). Además `pyproject.toml` declara `readme = "README.md"`, así que el paquete publica este texto como descripción. | Reemplazar por un README real (promover y actualizar `README-backend.md`). El contenido histórico → `docs/historico/`. |
| `README-backend.md` | 🟡 DESACTUALIZADO | Es el README de proyecto "de verdad", pero con datos caducados: diagrama dice **Supabase (PgSQL)** en vez de Azure PostgreSQL; describe el sistema como **ejecución de órdenes con Alpaca** (el producto es **alertas/squawks**, no ejecución); habla de **16 tickers**, **Grafana**, host `*.supabase.co`, frontend en `:3001`; `setup` usa `copy .env.example` con "claves de Supabase". No menciona auth/JWT, Stripe, Azure Blob/Speech ni el frontend Next.js 16. | Reescribir como `README.md` raíz: Azure PostgreSQL, producto = alertas, stack actual (auth, Stripe, Azure Blob/Speech/TTS), `frontend/` Next.js 16. |
| `Contexto_Auditoria_Siguiente_Chat.md` | 📦 MOVER A docs/ (🟡) | Nota de contexto de la auditoría Fase 3c. Útil como histórico pero desactualizada (habla de Supabase, "Parte 2/3 pendientes", `apps/api/main.py` "no borrar todavía"). No es documentación de producto. | Mover a `docs/historico/`. |
| `Fase_3c_Auditoria_Codigo_Squawks_ML.md` | 📦 MOVER A docs/ (🟡) | Documento extenso de auditoría Fase 3c. Valioso como histórico, pero muchos pendientes ya resueltos (CI en `master`, `psycopg2`, `services*` en packages…) y describe estado de hace varias fases. Ruido en la raíz. | Mover a `docs/historico/`. |
| `fase3c-parte4-completo.patch` | 🔴 OBSOLETO-BORRAR | Patch (`git format-patch`) de mayo 2026 ya **aplicado** (su contenido está en `pyproject.toml`, `ci.yml`, etc.). Un `.patch` suelto en la raíz es un artefacto de un solo uso. | Eliminar. |
| `sesion16/` | 🔴 OBSOLETO-BORRAR | **Residuo de staging del commit "Sesión 16"** (8ca9ee1). Son copias planas de archivos que ya viven en su sitio real. Nadie las importa (`grep sesion16` = 0 referencias). `legacy_runners.py`, `types.ts`, `equity-curve.tsx` son **idénticos** a su destino; `guardrails.py`, `backtest_engine.py`, `backtest_router.py`, `backtest_page.tsx` son **versiones más antiguas** ya superadas (p. ej. `guardrails.py` aún tiene el default `60`, mientras `shared/guardrails.py` ya está en `55`). | Eliminar el directorio completo. |
| `workers/` | 🟡 DESACTUALIZADO (stub) | `workers/backtest/main.py` y `workers/training/main.py` son **stubs** con `TODO fase 4`. Nadie los importa y **ningún Dockerfile los construye**. El flujo de training ya se sirve por otra vía (`services/api/routers/training_jobs.py` + tabla `training_jobs`). Stub nunca cableado, con referencias a fases ya superadas. | Mantener solo si hay plan real de Service Bus; si no, mover a `docs/historico/roadmap-workers/` o eliminar. **Decisión de producto.** |
| `docs/contexto_squawks_ml.md` | 🟡 DESACTUALIZADO | Doc de contexto antiguo: stack dice **Supabase**, frontend **React Native + Expo** (hoy es Next.js 16), path local Windows, "13/13 servicios", roadmap con fases ya cerradas. Ya está en `docs/`, así que solo necesita marcarse como histórico. | Renombrar/mover a `docs/historico/` y añadir nota "estado a fecha X". |
| `LICENSE` | ✅ VIGENTE | MIT 2026. Correcto. | Mantener. |
| `.gitignore` | 🟡 DESACTUALIZADO | Funciona, pero tiene basura: línea 81 con un nombre de archivo corrupto espaciado (`m i g r a c i o n _ p o s t g r e s q l . p a t c h`) y sección "Streamlit (para Fase 5)" que ya no aplica. | Limpiar la línea corrupta y la sección Streamlit. |
| `.dockerignore` | ✅ VIGENTE | El merge-conflict reportado en la auditoría Fase 3c ya está resuelto; ignora `docs/`, `tests/`, `*.md` (excepto README) y deja pasar los modelos. Coherente. | Mantener. |
| `.env.example` | 🔴 DESACTUALIZADO (crítico) | **Incompleto**: solo declara 7 variables. Faltan **~22 variables que el código lee de verdad** (Stripe, Azure Blob, Azure Speech, SMTP, JWT, CORS, Redis, FRONTEND_URL). Ver §2. Un dev que copie este archivo no puede arrancar auth, pagos, TTS ni emails. | Regenerar con todas las variables (plantilla en §2). |
| `docker-compose.dev.yml` | ✅ VIGENTE (🟡 menor) | Servicios `api`/`engine`/`ingestion` coinciden con los Dockerfiles y con `services.api.main`. Correcto. Nota menor: no levanta PostgreSQL local (depende de Azure vía `.env`) y no monta ni construye los servicios nuevos (auth/stripe viven dentro de `services/api`, así que OK). | Mantener. |
| `pyproject.toml` | 🟡 DESACTUALIZADO | (1) **Falta `stripe`** como dependencia aunque `shared/stripe_service.py` lo importa y `requirements.txt` sí lo tiene → desincronizados. (2) Extra `dashboard` referencia **Streamlit/plotly** que ya no se usan. (3) Extra `notebooks`/`yfinance` revisables. El `supabase` ya fue eliminado (✅). `services*` ya está en packages (✅). | Añadir `stripe>=8.0` a `dependencies`; eliminar extra `dashboard`. |
| `requirements.txt` | 🟡 DESACTUALIZADO | Autogenerado desde pyproject pero **divergente**: tiene `stripe>=8.0` y `email-validator` que no están en pyproject; pyproject usa `pydantic[email]`. Es una segunda fuente de verdad que se desincroniza. **El CI usa `pip install -e ".[dev]"` (pyproject), NO requirements.txt** — pero los Dockerfiles **sí** usan `requirements.txt` (`Dockerfile.base`). Riesgo: imagen y CI instalan sets distintos. | Decidir fuente única. Regenerar `requirements.txt` desde pyproject (tras añadir `stripe`) o documentar el flujo. |
| `.github/workflows/ci.yml` | ✅ VIGENTE | Dispara en `master` (✅, no `main`), usa `DATABASE_URL` placeholder (✅, no Supabase), inyecta `JWT_SECRET_KEY` para tests, lint sobre `services/` incluido. | Mantener. |
| `.github/workflows/deploy.yml` | ✅ VIGENTE | Build & push a ACR en `master`, 3 imágenes (api/engine/ingestion), doble tag `latest`+`sha`. Coherente con `docker/`. | Mantener. |
| `docker/Dockerfile.base` | ✅ VIGENTE | Instala desde `requirements.txt` (ver nota de sync arriba), torch CPU-only, FinBERT. | Mantener (depende de fix de `requirements.txt`). |
| `docker/Dockerfile.{api,engine,ingestion}` | ✅ VIGENTE | `api` arranca `services.api.main:app`; `engine`/`ingestion` con healthcheck real (`query('SELECT 1')`). Coinciden con `docker-compose` y `deploy.yml`. | Mantener. |

### Hallazgos secundarios (fuera de la raíz, pero relevantes para la limpieza)

| Archivo | Veredicto | Motivo |
|---|---|---|
| `apps/api/main.py` | 🔴 OBSOLETO-BORRAR | Legacy de 597 líneas. Importa `from shared.db import sb` (línea 32), pero **`shared/db.py` ya no exporta `sb`** → el módulo lanza `ImportError` al importarse. **Nadie lo importa** ya: los routers `backtest`/`training` ahora usan `shared/legacy_runners.py` + `shared/db`. Es código muerto y roto. La razón histórica para conservarlo ("D8/D9 dependen de él") **ya no aplica**. | Eliminar (verificar que `shared/legacy_runners.py` cubre todo lo necesario). |
| `apps/ml_sandbox/{train,evaluate,config}.py`, `apps/ingestion_historical/ingestion.py`, `apps/ingestion_live/alpaca_prices.py` | 🟡 DESACTUALIZADO | Referencias a "Supabase" **en docstrings/comentarios** (el código ya usa `shared.db`). Cosmético pero confunde. | Actualizar docstrings → "PostgreSQL". |
| `scripts/verify_system.py` | ✅ (nota) | A diferencia de lo que decía la auditoría Fase 3c, **ya no usa Supabase** (usa `AZURE_STORAGE_CONN_STR`, `API_URL`). El documento histórico está desactualizado en este punto. | — |

---

## 2. `.env.example` — variables que faltan

Búsqueda de `os.getenv` / `os.environ` en todo el código. Variables **leídas por el código** vs **declaradas** en `.env.example`.

### ✅ Presentes y vigentes (7)
`DATABASE_URL`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`, `HUGGINGFACE_TOKEN`, `ALLOW_LIVE_TRADING`, `BATCH_INSERT`.

### 🔴 Faltan (~22) — agrupadas por dominio

| Variable | Leída en | Notas |
|---|---|---|
| `CORS_ORIGINS` | `services/api/main.py:50` | Default `localhost:3000,3001`. En prod, dominios reales. |
| `REDIS_URL` | `shared/config.py:79`, `services/api/middleware/rate_limiter.py:215` | Cache / rate limiting. |
| `FRONTEND_URL` | `shared/stripe_service.py:96` | Redirects de Stripe Checkout. |
| `JWT_SECRET_KEY` | `services/api/auth/security.py:27` | **Crítico** para auth. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `auth/security.py:36` | Default `30`. |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `auth/security.py:37` | Default `7`. |
| `AZURE_STORAGE_CONN_STR` | `shared/blob_storage.py:29`, `shared/tts.py:34`, `scripts/verify_system.py:85` | Modelos + audios de squawks. |
| `AZURE_STORAGE_MODELS_CONTAINER` | `shared/blob_storage.py:30` | Default `models`. |
| `AZURE_SPEECH_KEY` | `shared/tts.py:32` | TTS de squawks. |
| `AZURE_SPEECH_REGION` | `shared/tts.py:33` | Default `spaincentral`. |
| `SMTP_HOST` | `services/api/auth/email.py:31` | Verificación de email. |
| `SMTP_PORT` | `auth/email.py:32` | Default `587`. |
| `SMTP_USER` | `auth/email.py:33` | |
| `SMTP_PASSWORD` | `auth/email.py:34` | |
| `SMTP_FROM` | `auth/email.py:35` | |
| `APP_BASE_URL` | `auth/email.py:36` | Links de verificación. |
| `STRIPE_SECRET_KEY` | `shared/stripe_service.py:41` | |
| `STRIPE_WEBHOOK_SECRET` | `stripe_service.py:277` | Verificación de webhooks. |
| `STRIPE_STARTER_PRICE_ID` | `stripe_service.py:68` | |
| `STRIPE_PRO_PRICE_ID` | `stripe_service.py:69` | |
| `STRIPE_PACK_BACKTESTS_PRICE_ID` | `stripe_service.py:71` | |
| `STRIPE_PACK_TRAININGS_PRICE_ID` | `stripe_service.py:72` | |
| `STRIPE_PACK_TICKER_PRICE_ID` | `stripe_service.py:73` | |

> Nota: `HF_TOKEN` se **escribe** (no se lee) en `finbert*.py` a partir de `HUGGINGFACE_TOKEN`. `API_URL`/`CHECK_ENDPOINTS`/`TEST_ENDPOINTS` solo se usan en scripts/tests (no hace falta en `.env.example`).

### Plantilla `.env.example` propuesta (no aplicada)

```dotenv
# ─── PostgreSQL (obligatorio) ───────────────────────────────
DATABASE_URL=postgresql://sqadmin:PASSWORD@squawks-ml-db.postgres.database.azure.com:5432/postgres?sslmode=require

# ─── Alpaca (obligatorio) ───────────────────────────────────
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
ALLOW_LIVE_TRADING=false

# ─── HuggingFace (FinBERT) ──────────────────────────────────
HUGGINGFACE_TOKEN=hf_...

# ─── Auth / JWT ─────────────────────────────────────────────
JWT_SECRET_KEY=cambia-esto-por-un-secreto-largo
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ─── CORS / Frontend ────────────────────────────────────────
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
FRONTEND_URL=http://localhost:3000
APP_BASE_URL=http://localhost:3000

# ─── Azure Blob Storage (modelos + audios) ──────────────────
AZURE_STORAGE_CONN_STR=
AZURE_STORAGE_MODELS_CONTAINER=models

# ─── Azure Speech (TTS de squawks) ──────────────────────────
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=spaincentral

# ─── SMTP (verificación de email) ───────────────────────────
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=Squawks ML <noreply@squawksml.com>

# ─── Stripe (pagos) ─────────────────────────────────────────
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_STARTER_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_PACK_BACKTESTS_PRICE_ID=price_...
STRIPE_PACK_TRAININGS_PRICE_ID=price_...
STRIPE_PACK_TICKER_PRICE_ID=price_...

# ─── Redis (opcional: cache + rate limiting) ────────────────
REDIS_URL=

# ─── Otros ──────────────────────────────────────────────────
BATCH_INSERT=500
```

---

## 3. Referencias a Supabase que quedan

| Tipo | Dónde | Acción |
|---|---|---|
| **Código real roto** (`sb.table(...)`) | `apps/api/main.py` (legacy, importa `sb` inexistente) | Borrar el archivo (§ hallazgos secundarios). |
| **Solo docstrings/comentarios** | `apps/ml_sandbox/{train,evaluate,config}.py`, `apps/ingestion_historical/ingestion.py`, `apps/ingestion_live/alpaca_prices.py`, `shared/db.py` (comenta "reemplaza al cliente Supabase") | Limpiar redacción → "PostgreSQL". |
| **Docs** | `README-backend.md`, `docs/contexto_squawks_ml.md`, `Contexto_Auditoria_*.md`, `Fase_3c_*.md` | Actualizar o mover a histórico. |

`shared/db.py` ya **no** exporta `sb` ni usa el cliente Supabase: la migración a `psycopg2` está hecha. El residuo es puramente textual + el archivo legacy muerto.

---

## 4. Resumen ejecutivo

- **Borrar ya (residuo puro):** `README.md` (residuo de zip de fixes), `fase3c-parte4-completo.patch`, `sesion16/`, `apps/api/main.py` (muerto y roto).
- **Arreglar (desactualizado pero útil):** `.env.example` (faltan ~22 vars — **prioridad alta**), `pyproject.toml` (falta `stripe`, sobra extra `dashboard`), `requirements.txt` (sync), `.gitignore` (línea corrupta).
- **Mover a `docs/historico/`:** `Contexto_Auditoria_Siguiente_Chat.md`, `Fase_3c_Auditoria_Codigo_Squawks_ML.md`, `docs/contexto_squawks_ml.md`.
- **Reescribir:** promover `README-backend.md` → nuevo `README.md` raíz, actualizado a Azure + producto de alertas.
- **Decisión de producto:** `workers/` (mantener como roadmap o eliminar).
- **Vigentes:** `LICENSE`, `.dockerignore`, `docker-compose.dev.yml`, `docker/Dockerfile.*`, `.github/workflows/*.yml`.

---

## 5. Bloque de comandos de limpieza (NO ejecutado)

> Revisar antes de ejecutar. Pensado para correr desde la raíz del repo en una rama de limpieza.

```bash
# ── 0. Rama de trabajo ──────────────────────────────────────
git checkout -b chore/limpieza-raiz

# ── 1. Borrar residuos puros ────────────────────────────────
git rm -r sesion16/                        # staging residue del commit "Sesión 16"
git rm fase3c-parte4-completo.patch        # patch ya aplicado
git rm apps/api/main.py                    # legacy muerto (importa shared.db.sb inexistente)

# ── 2. Archivar histórico de auditoría en docs/ ─────────────
mkdir -p docs/historico
git mv Contexto_Auditoria_Siguiente_Chat.md      docs/historico/
git mv Fase_3c_Auditoria_Codigo_Squawks_ML.md    docs/historico/
git mv docs/contexto_squawks_ml.md               docs/historico/

# ── 3. README: promover el de backend y eliminar el residuo ─
git mv README.md docs/historico/README_fase3c_zip.md   # conservar como histórico
git mv README-backend.md README.md                     # luego ACTUALIZAR a Azure/alertas
#   → editar README.md: Supabase→Azure PostgreSQL, ejecución→alertas/squawks,
#     añadir auth/JWT, Stripe, Azure Blob/Speech/TTS, frontend Next.js 16.

# ── 4. Fixes de configuración (editar a mano, ver §2 y tabla) ─
#   .env.example     → añadir las ~22 variables (plantilla en §2)
#   pyproject.toml   → añadir "stripe>=8.0"; eliminar extra [dashboard]
#   requirements.txt → regenerar desde pyproject (fuente única)
#   .gitignore       → borrar línea 81 corrupta + sección Streamlit

# ── 5. (Opcional / decisión de producto) workers/ ───────────
# git rm -r workers/        # si se descarta el plan de Service Bus
#   o:  git mv workers docs/historico/roadmap-workers

# ── 6. Limpieza cosmética de docstrings "Supabase" → "PostgreSQL" ─
#   apps/ml_sandbox/{train,evaluate,config}.py
#   apps/ingestion_historical/ingestion.py
#   apps/ingestion_live/alpaca_prices.py
#   shared/db.py (comentario)

git commit -m "chore: limpieza de archivos obsoletos de la raíz + sync de config"
```
