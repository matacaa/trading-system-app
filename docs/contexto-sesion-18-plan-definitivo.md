# Squawks ML — Contexto Sesión 18: Plan definitivo (bugs + mejoras)

**Fecha:** 04/06/2026
**Repo:** `https://github.com/matacaa/trading-system-app` (branch `master`)
**Último commit verificado:** `fe0829a` (23/05/2026) — "Settings: test audio notification + squawk TTS"
**Métricas verificadas:** 144 archivos Python · 25 TS/TSX · 54 endpoints en 16 routers · API v7.0.0

---

## 0. INSTRUCCIONES PARA ESTA SESIÓN (leer primero)

1. **Clona el repo y analízalo en profundidad ANTES de escribir código.** No te limites a los ficheros mencionados aquí: recorre `services/api/routers/`, `apps/trading_engine/`, `apps/ml_sandbox/`, `apps/ingestion_historical/`, `apps/ingestion_live/`, `shared/`, `frontend/src/`, `scripts/*.sql` y `config/`.
2. **Contrasta el código real con este documento.** Todo lo afirmado aquí fue verificado contra el commit `fe0829a`, pero puede haber commits posteriores. Verifica cada bug y cada hallazgo línea a línea. Si encuentras discrepancias (bug ya corregido, fichero movido, esquema cambiado), **repórtalas antes de proponer cambios**.
3. **Verifica especialmente si el zip `sesion17-fixes` ya fue integrado** (ver Sprint 0). En `fe0829a` NO lo estaba.
4. Respeta el flujo de trabajo: Claude escribe el código → entrega ficheros individuales o zip → Javier extrae en la raíz del repo (¡cuidado con carpetas anidadas!) → prueba en local contra Azure PostgreSQL → push a GitHub tras cada hito validado.
5. Entorno: Windows 11 + PowerShell (`python -m uvicorn`, venv con `.\Activate.ps1`), frontend en puerto **3001**, `ruff check .` obligatorio antes de cada entrega, `npx next build` sin errores TS antes de entregar frontend.
6. Migraciones SQL: entregar como `.sql` para ejecución manual contra Azure PostgreSQL.

---

## 1. ARQUITECTURA ACTUAL (verificada en código)

- **Backend:** FastAPI, Python 3.11, psycopg2 directo contra Azure PostgreSQL Flexible Server (Spain Central). Sin Supabase.
- **Frontend:** Next.js 16 App Router, Tailwind v4, Zustand, Axios con interceptor, Recharts. La pestaña Squawks es `frontend/src/app/dashboard/page.tsx` (raíz del dashboard). Existe `dashboard/layout.tsx`.
- **Pipeline ML (4 pasos):** guardrails PRE (13, solo datos de mercado) → inferencia sistema compartida + 25 señales rule-based → modelos custom por usuario → guardrail POST (`score_minimo` por dirección) → decisión LONG/SHORT + TTS.
- **Ejecución de jobs HOY:** `POST /api/train` y `POST /api/backtest` ejecutan `_run_training_sync()` / `_run_backtest_sync()` **dentro del request handler** (bloquean el worker de uvicorn 60+ segundos). Generan YAML temporal → subprocess `python -m apps.ml_sandbox.pipeline --config tmp.yaml`.
- **Datos:** ingesta histórica soporta 1m/5m/15m (`raw_ohlcv_{tf}` + `silver_features_{tf}`); **1h NO existe**. Engine live: `silver_features_rt` SIN columna timeframe (conflict `ticker,ts`), ciclo de 1 minuto.
- **Blob Storage:** `shared/blob_storage.py` completo (upload/download/cache/delete/`build_blob_path`). La inferencia descarga vía `ensure_local()`. **El training NUNCA sube** — `blob_path` siempre NULL.
- **YAMLs estáticos en runtime:** `config/live/trading.yaml` + `config/live/ensemble.yaml` (el engine los carga al arrancar, trading_engine/main.py:87-100), `config/experiments/*.yaml` (6 modelos de sistema), `config/ingestion/tickers.yaml`.
- **DB ya provisionada y sin usar:** `users.locale` (default 'es'), `users.timezone` (default 'Europe/Madrid'), `user_preferences.language` (duplicado a deprecar), `user_settings.default_timeframe`.
- El engine **ya usa `u.locale`** para generar texto/TTS de squawks en es/en.

---

## 2. BUGS IDENTIFICADOS (verificados contra `fe0829a`)

| ID | Descripción | Evidencia | Estado |
|---|---|---|---|
| BUG-01 | No existe forgot/reset password (ni endpoints ni página) | grep sin resultados en auth.py y frontend | Pendiente — Sprint S7 |
| BUG-02 | Router squawks SELECTea columnas inexistentes: `title, body, direction, guardrails_result, is_favorite` (squawks.py:72-75). El schema real (`migration_fase5_squawks.sql`) tiene `decision, motivo, is_starred, guardrails_passed`. El PATCH (línea ~147) también escribe `is_favorite` | Verificado | Pendiente — S4. **Fix en el router con aliases, NO ALTER TABLE** (el INSERT del engine ya usa las columnas reales) |
| BUG-03 | CHECK de `squawk_type` solo admite BUY/SELL/HOLD/INFO/WARNING; el engine genera LONG/SHORT/HOLD/INFO → INSERT fallará | Verificado | Pendiente — S0 (migración) |
| BUG-04 | Training no sube modelos a Blob (`blob_path` nunca se rellena; cero referencias a blob en training.py/train.py) | Verificado | Pendiente — S6 (ver mejora #2) |
| BUG-05 | Deploy Azure Container Apps pendiente (Fase 8.10) | — | S8 |
| BUG-06 | Webhook Stripe apunta a URL provisional | — | S8 (post-deploy) |
| BUG-07 | `register/page.tsx:56` muestra devToken sin guard de NODE_ENV | Verificado | S0 |
| BUG-08 | Consulta legal CNMV + GDPR pendiente | — | **Paralelo desde YA** (mayor lead time) |
| BUG-09 | Modelos de sistema no mapean a experiment_names en backtest | Verificado | S0 (opción simple: quitarlos del dropdown) |
| BUG-10 | `store.register` llama a setTokens con tokens que register no devuelve | store.ts:62+ | S0 |
| BUG-11 | Resend verificación: `catch { /* ignore */ }` — errores invisibles (login/page.tsx:~58) | Verificado | S0 |
| BUG-12 | Root page solo comprueba presencia de token, no expiración | Verificado | S0 |
| BUG-13 | Training: Features UI sin verificar, fechas se resetean tras entrenar, re-train duplica entradas en sidebar en vez de sobrescribir | Sesión 14 | S5 |
| BUG-14 | Equity curve reconstruida desde trades en el router en vez de persistir la real del engine | Verificado | S0 |
| — | **Zip sesion17-fixes NO integrado**: `_close_position` sigue haciendo append sin actualizar el trade abierto; no se persisten métricas direccionales (`long_trades`, `long_pnl`...); falta ALTER TABLE de 6 columnas | Verificado en fe0829a | S0 — **verificar si ya se integró** |

**Hallazgo crítico adicional (verificado):** en `apps/ml_sandbox/backtest.py` la inferencia se ejecuta ANTES que los guardrails (predict_ensemble en línea ~309, check_guardrails_for_direction en ~314/331), **al revés** que el engine live (que sí hace PRE→inferencia→POST correctamente, trading_engine/main.py:245-299) y al revés que el propio docstring del fichero. Ver mejora #6.

---

## 3. MEJORAS ACORDADAS (decisiones de diseño cerradas)

### #1 — Colas + workers separados (training y backtest en contenedores distintos)
- **Cola sobre PostgreSQL, SIN Redis** (escala actual no lo justifica; ahorro ~35€/mes). `SELECT ... FOR UPDATE SKIP LOCKED`.
- `training_jobs` y `backtest_runs` ganan: status `'queued'`, `claimed_at`, `worker_id`.
- API: `POST /api/train` y `POST /api/backtest` validan créditos/límites → INSERT `status='queued'` → devuelven job_id en <100ms. **El contrato HTTP no cambia** (el frontend no se toca).
- **Un solo codebase** `apps/worker/main.py` parametrizado con env var `WORKER_QUEUE=training|backtest` → **2 Container Apps**: `squawks-worker-training` (más CPU/RAM) y `squawks-worker-backtest` (ligero).
- **Scale-to-zero con KEDA** (scaler PostgreSQL nativo de Container Apps): 0 réplicas si no hay jobs queued; arranque frío ~10-30s, irrelevante para jobs de minutos.
- El worker ejecuta el job vía **subprocess** (aislamiento de crashes/OOM: muere el subprocess, no el loop; job → `failed`).
- El cleanup de jobs atascados (>15 min) se muda al worker.
- Frontend: Training ya hace polling; Backtest debe pasar a polling completo. Timeout de Axios vuelve a valores normales.
- **Total backend: 5 contenedores** (api, engine, ingestion, worker-training, worker-backtest) + frontend (decisión pendiente en S8: Container App vs Static Web Apps).

### #2 — Blob upload de modelos entrenados (absorbe BUG-04)
- Upload **dentro de `train.py`, junto a `_register_model()`** (atómico con el INSERT del registry; funciona lo lance worker, API o CLI). NO en el router.
- **Plumbing de `user_id`** hasta el subprocess (no llega hoy): vía config/env. Necesario para `build_blob_path` (`users/{uid}/...` vs `system/...`).
- **Blocker duro para #1:** con scale-to-zero el disco del worker es efímero — sin upload, los modelos se pierden al apagarse el contenedor.

### #3 — Limpieza de blobs en retrain/delete
- **Bug latente descubierto:** `build_blob_path()` NO incluye versión → retrain sobrescribiría el mismo blob Y el cache de `ensure_local()` (clave = MD5 del blob_path) serviría el modelo VIEJO tras un retrain. 
- **Fix: ruta versionada** `users/{uid}/{ticker}/{exp}/v{N}/model.pkl` → invalidación de cache automática.
- Retrain: borrar blobs de versiones previas **solo tras éxito** del upload+registro nuevo (si el training falla, el usuario conserva su modelo). Filas del registry se conservan con `blob_path=NULL` (histórico de métricas gratis). **Se renuncia al rollback binario** (decisión explícita; el código actual decía conservar versiones para rollback/A-B, pero estaba roto de diseño por el overwrite).
- Delete: ampliar `DELETE /models/{name}` para iterar **todas** las versiones (hoy solo borra el blob de `is_active=true`).
- Cierra MEJORA-10 (huérfanos).

### #4 — Eliminación TOTAL de YAML en runtime (decisión: nivel 2, completo)
- **Peticiones:** columna `config JSONB` en `training_jobs` y `backtest_runs` con el job completo. Refactor de `load_config`/`ExperimentConfig` para **construirse desde dict** — el YAML temporal desaparece. Bonus: reproducibilidad/auditoría (re-lanzar = re-encolar el mismo config).
- **Config estática del engine:** `config/live/trading.yaml` + `ensemble.yaml` → tabla `system_config` en PostgreSQL, releída por el engine con TTL ~1 min. Motivo: hoy cambiar un peso del ensemble exige rebuild+redeploy de la imagen; en DB es un UPDATE en caliente (misma filosofía que `plan_config`).
- **Modelos de sistema:** `config/experiments/*.yaml` se eliminan; entrenar modelos de sistema = insertar config JSONB en la misma cola que los custom (el admin usa la misma tubería que los usuarios).
- **`config/ingestion/tickers.yaml`** → DB (unificar con tabla de tickers existente).
- Resultado: **cero YAMLs en runtime** (training, backtest, squawks/engine, ingesta). PyYAML fuera de requirements. Imprescindible además porque API y workers NO comparten filesystem.

### #5 — Multi-timeframe 1m/5m/15m/1h (histórico + real time)
- **A. Ingesta histórica 1h** (~2-3h): añadir `"1h"` a `INTERVALS`/`RAW_TABLES`/`SILVER_TABLES`, `TimeFrame.Hour` de Alpaca, migración `raw_ohlcv_1h` + `silver_features_1h`. **Lanzar backfill el día 1 del sprint** (corre en background). 5m/15m ya existen.
- **B. Selector en Training** (~2h): dropdown 1m/5m/15m/1h → `silver_model_registry` gana columna **`timeframe`** (hoy solo va implícito en el nombre del experimento, frágil). El endpoint de rango de fechas disponibles debe ser consciente del timeframe.
- **C. Selector en Backtest** (~1-2h): **se elige primero la granularidad → el dropdown de modelos SE FILTRA y solo muestra modelos entrenados en esa granularidad** (coherencia automática con N modelos del ensemble). Validación también server-side: el router rechaza el job si algún modelo no coincide.
- **D. Engine live multi-TF** (~6-10h): agregación de barras 1m → 5m/15m/1h al cierre de cada periodo; `silver_features_rt` con columna `timeframe` (conflict `ticker,ts,timeframe`); **inferencia de cada modelo custom al cierre de la barra de SU timeframe** sobre features RT de esa granularidad, con guardrails PRE sobre esos mismos indicadores. Un usuario con modelo 1m y modelo 1h en el mismo ticker recibe squawks a dos cadencias. `gold_squawks` gana columna `timeframe` (y el TTS puede declararla).
- **Decisión cerrada:** inferencia de sistema y las 25 señales rule-based se quedan en **1m en el lanzamiento**; multi-TF aplica a modelos custom. Señales de sistema por TF → post-launch.

### #6 — Orden guardrails → modelo (CONFIRMADO explícitamente)
- **Engine live: ya correcto**, no tocar (PRE → continue si rechaza → inferencia → POST).
- **Backtest: reordenar el loop por barra** a: `check_guardrails_for_direction(long)` y `(short)` primero → si NINGUNA dirección pasa, siguiente barra SIN inferencia → si alguna pasa, UNA llamada a `predict_ensemble` → `check_score_for_direction` (umbral long/short independiente, ya existe en guardrails.py:275) solo en las direcciones supervivientes → señal solo si pasa también el umbral.
- Efectos: rendimiento (la inferencia es lo caro, sobre todo LSTM/GRU/Transformer) y **coherencia semántica backtest=live** (clave para "Stop trusting. Start testing.").
- Colateral: barras rechazadas por guardrail quedan sin score → el chart de backtest debe tolerar score nulo.

### #7 — Dirección + confianza (COMPLETO, incluida calibración)
- La dirección ya es implícita (score = P(subida) 0-100, umbrales long/short).
- **a) Dispersión del ensemble:** `predict_ensemble` ya tiene scores por modelo (`detalle`) — devolver también **score ± desviación estándar** y **ratio de acuerdo** ("5 de 6 modelos apuntan arriba"). Persistir en `model_scores` JSONB. Visible en: detalle del squawk, cada señal del backtest, resultados de training. Opcional: incluir en TTS.
- **b) Métricas direccionales en evaluación:** accuracy/f1 desglosadas por LONG y SHORT en resultados de training (hoy solo globales) — el usuario las necesita para elegir umbrales con criterio.
- **c) Calibración de probabilidades** (Platt/isotónica o conformal): set de calibración en el pipeline de training + curva de calibración en resultados. Que "73" signifique ~73% real.

### #8 — Squawks: toggles con mercado abierto + autoplay global
- **Mercado:** endpoint `GET /api/market/status` (clock/calendar de Alpaca — cubre festivos y medias sesiones), cache ~1 min. Toggle deshabilitado + tooltip con hora de apertura **en la timezone del usuario** cuando el mercado del ticker esté cerrado. **Decisión:** los toggles ya activos NO se desactivan al cierre (el guardrail `horario_mercado` ya impide generar fuera de horario); solo se bloquea la activación nueva.
- **Autoplay:** el polling de 12s vive HOY dentro de `dashboard/page.tsx` → si el usuario está en otra pestaña de la app, ni se detecta el squawk. **Mover a un `SquawkListener` global en `dashboard/layout.tsx`** (contexto React): detección esté donde esté, incluso con el navegador en background. **Cola de reproducción secuencial** (sin solapes). Restricción de autoplay del navegador: activar un toggle = la interacción que desbloquea el audio; fallback a push (ya existe) + banner "pulsa para activar audio". Toggle de mute global en Settings. Cierra MEJORA-01. Futuro: el listener migra de polling a WebSocket/SSE (MEJORA-03) sin tocar la cola de audio.

### #9 — Settings: idioma + timezone
- `users.locale` y `users.timezone` YA existen; el engine YA genera squawks/TTS según locale. Falta exponer.
- **Pre-launch (capas 1+2):** PATCH para locale/timezone + dos selectores en Settings; `email.py` usa el locale para plantillas; barrido de frontend para formatear TODOS los timestamps con `Intl.DateTimeFormat` en la tz del usuario (squawks, charts, backtest, tooltip de mercado); autodetección de tz en registro (`Intl.DateTimeFormat().resolvedOptions().timeZone`); **unificar** `users.locale` (gana, es la que lee el engine) vs `user_preferences.language` (deprecar); `lang` del HTML dinámico (resuelve MEJORA-06 bien).
- **Post-launch:** i18n completa de la UI (next-intl, ~8-12h). Lanzamiento: UI en español, squawks/emails bilingües.

---

## 4. PLAN DE SPRINTS (orden definitivo con dependencias)

**Principio rector:** todo lo que modifica el comportamiento de training/backtest va ANTES del sprint de workers (S6), que refactoriza UNA sola vez el código ya final y lo "congela" en la cola. `generate_experiment_yaml` ya acepta `timeframe`, así que el multi-TF funciona sobre la arquitectura síncrona actual sin retrabajo.

| Sprint | Contenido | Puntos | Horas |
|---|---|---|---|
| **S0** | Integrar zip sesión 17 + ALTER TABLE 6 columnas; BUG-03 (CHECK + migración), BUG-07, BUG-09 (quitar modelos sistema del dropdown), BUG-10, BUG-11, BUG-12, BUG-14 (persistir equity real), MEJORA-06 provisional | bugs | ~4h |
| **S1** | Reorden guardrails→modelo en backtest + dispersión del ensemble en `inference.py` + validación pestaña Backtest. *Inmediatamente tras S0: mismo fichero (`backtest.py`)* | #6, #7a | ~10h |
| **S2** | Ingesta 1h (backfill día 1) + selector timeframe en Training + selector con filtrado de modelos en Backtest + columna `timeframe` en registry | #5 A/B/C | ~6h |
| **S3** | Engine live multi-TF (agregación, `silver_features_rt` con timeframe, inferencia al cierre de cada periodo, `gold_squawks.timeframe`). *Solo toca `trading_engine` + `silver_rt`* | #5 D | ~6-10h |
| **S4** | Market status + toggles bloqueados; SquawkListener global + cola de audio + autoplay; BUG-02 (aliases en router + PATCH `is_starred`); dispersión visible en squawks. Validación end-to-end (valida de paso el multi-TF live de S3 con squawks reales) | #8, #7a-UI, BUG-02 | ~10h |
| **S5** | Métricas direccionales + calibración en pipeline de training; BUG-13 (Features UI, fechas, duplicados sidebar). Validación página Training. *Última modificación de `train.py`/`evaluate` antes del refactor* | #7b, #7c, BUG-13 | ~12-14h |
| **S6** | Colas Postgres + 2 workers KEDA + `config` JSONB + **eliminación total de YAML** (peticiones, `system_config` para el engine, experiments de sistema, tickers de ingesta) + blob upload con user_id + rutas versionadas + limpieza retrain/delete | #1, #4, #2, #3 | ~23-25h |
| **S7** | Idioma/timezone en Settings + emails por locale + barrido timestamps + autodetección tz + unificación locale/language; BUG-01 forgot password | #9, BUG-01 | ~9h |
| **S8** | Deploy: 5-6 contenedores (decidir hosting frontend), env vars, dominio/HTTPS, ACR+Actions, BUG-06 webhook Stripe, MEJORA-09 cron ingesta, smoke tests | BUG-05/06 | ~10h |
| **S9** | Fase 9: testing end-to-end, Stripe live, Billing en producción, launch prep | — | ~25h |

**Paralelo desde ya:** BUG-08 (consulta CNMV + GDPR) — mayor lead time de todo el plan.

**Dependencias estrictas:** S0→S1 (mismo fichero) · S2→S3 (datos antes que live) · S1-S5→S6 (el worker congela lo final) · todo→S8.
**S7 es móvil.** **S3 es el único recortable** a post-launch (lanzando squawks live limitados a 1m, con aviso en UI, y los 4 timeframes en Training/Backtest).

**Total estimado hasta launch: ~110-120h.**

**Diferido post-launch:** i18n completa UI, señales de sistema por timeframe, Redis (cuando se quiera también para cache de polling), WebSocket/SSE (MEJORA-03), PgBouncer, MEJORA-07 (middleware), upgrade tier PostgreSQL, Fase 10 (React Native, ~60h).

---

## 5. LEARNINGS A RESPETAR (acumulados de sesiones previas)

- `get_conn()` SIEMPRE como context manager (bug latente en backtest.py, models.py, live.py — corregir al tocar esos ficheros).
- `gold_squawks` usa `decision`/`motivo`/`is_starred`/`guardrails_passed` — el fix de BUG-02 es en el ROUTER, no en la tabla.
- Email case-insensitive: `LOWER()` en lookup, normalización en registro.
- `COPY data/models/` en Dockerfile.engine (hasta que blob esté operativo en S6).
- Sidebar de training: una entrada por nombre de modelo (retrain sobrescribe, no duplica); `trainingName` string, no boolean.
- Firewall de Azure PostgreSQL debe permitir la IP local para dev.
- Silver features: solo 11 tickers; AAPL solo tiene datos 10–24 abril 2026 — tenerlo en cuenta al validar trainings/backtests (y MEJORA-09 cron lo resuelve en producción).
- Ruff como gate bloqueante; frontend `npx next build` limpio antes de entregar.
- Verificar que los ficheros entregados aterrizan en la RAÍZ del repo (problema recurrente con zips anidados).

---

## 6. PRIMER PASO DE LA SESIÓN

1. Clonar repo, verificar commit actual y contrastar TODO este documento contra el código (sección 0).
2. Reportar discrepancias encontradas.
3. Comenzar por **S0**, entregando: integración/verificación del zip sesión 17, migración SQL (ALTER TABLE 6 columnas + CHECK de squawk_type), y los fixes pequeños (BUG-07/09/10/11/12/14, MEJORA-06), cada uno con instrucciones de validación local.
