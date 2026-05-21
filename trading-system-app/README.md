# Fase 3c — Fixes aplicados

## Cómo usar este zip

1. Descomprime manteniendo la estructura de carpetas
2. Copia cada archivo a la misma ruta en tu repo `trading-system-app/`
3. Borra manualmente los 3 archivos listados abajo
4. Haz commit: `git add -A && git commit -m "Fase 3c: 16 fixes de auditoría"`

## 19 archivos modificados (reemplazar)

| Archivo | Fix # | Qué cambió |
|---------|-------|------------|
| `config/live/ensemble.yaml` | #1, #14 | Eliminada entrada fantasma `aapl_random_forest_1m_v1`. 6 modelos, pesos suman 1.0 |
| `.dockerignore` | #9 | Eliminados marcadores de merge conflict (`<<<<<<<`/`>>>>>>>`) |
| `.github/workflows/ci.yml` | #10 | Branch `main` → `master`. Env vars Supabase → DATABASE_URL |
| `pyproject.toml` | #11, #12 | `supabase>=2.3` → `psycopg2-binary>=2.9`. Añadido `services*` a packages |
| `docker-compose.dev.yml` | #13 | Añadido volumen `apps/ingestion_live` al servicio engine |
| `config/experiments/*.yaml` (×6) | #15 | `experiment.name` alineado con filename: v1 → v2 |
| `tests/conftest.py` | #16 | `.append()` deprecated → `DatetimeIndex` concat |
| `apps/trading_engine/main.py` | #8 | Docstring: "Supabase" → "PostgreSQL" |
| `apps/ingestion_live/silver_rt.py` | #8 | Docstrings: "Supabase" → "PostgreSQL" |
| `shared/models/registry.py` | #8 | Docstrings: "Supabase" → "PostgreSQL" |
| `shared/inference.py` | #8 | Variable: `signals_para_supabase` → `signals_para_db` |
| `services/api/main.py` | #3 | CORS: `["*"]` → lee de env var `CORS_ORIGINS` (default localhost) |
| `shared/signals/rules/golden_cross.py` | #2 | Docstrings y variables: honestamente documentan que usa EMA, no SMA |
| `shared/db.py` | #6 | `get_conn()` ahora tiene retry (3 intentos, backoff exponencial) para errores transitorios |

## 3 archivos a BORRAR manualmente

```bash
cd trading-system-app
rm apps/trading_engine/trading_engine_main.py   # Fix #4: duplicado exacto de main.py
rm debug_news.py                                 # Fix #5: código muerto
rm apps/ingestion_historical/tensor.py           # Fix #7: redundante con dataset.py + usa Supabase
```

**⚠️ NO borrar** `apps/api/main.py` (597 líneas legacy) — los routers D8/D9 lo importan. Se borrará cuando se reescriban en Fase 6.

## 2 documentos de auditoría

| Archivo | Para qué |
|---------|----------|
| `Fase_3c_Auditoria_Codigo_Squawks_ML.md` | Documento principal — 49 pendientes, 12 bloques revisados |
| `Contexto_Auditoria_Siguiente_Chat.md` | Contexto para el siguiente chat de Claude |

## Nota sobre CORS

Después de aplicar el fix, añade a tu `.env`:
```
CORS_ORIGINS=*
```
Para desarrollo. En producción, usa tus dominios reales separados por comas.
