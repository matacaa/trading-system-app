# Contexto para continuar la auditoría — Fase 3c Squawks ML

## Qué estamos haciendo

Auditoría archivo por archivo del repo `trading-system-app`. Revisamos cada función, verificamos bugs, y anotamos pendientes técnicos. El usuario está aprendiendo el codebase a la vez, así que explico conceptos cuando pregunta.

## Repo

https://github.com/matacaa/trading-system-app — clónalo al empezar.

## Documento de auditoría

El usuario subirá `Fase_3c_Auditoria_Codigo_Squawks_ML.md` con todo el progreso. Léelo antes de continuar.

## Qué está revisado — Parte 1 COMPLETADA

- **Bloque A** (shared/): config, db, symbols, time, logging, indicators, guardrails — REVISADO
- **Bloque B** (models/): base, dataset, registry — REVISADO. Los 6 modelos individuales se saltaron (mismo patrón)
- **A★** (inference.py): REVISADO
- **Bloque C** (signals/): base + 25 reglas — REVISADO
- **Bloque D** (API): main + 9 routers — REVISADO. D8/D9 rotos parcial (POST roto, GET funciona)
- **Bloque E** (trading engine): db, alpaca_trader, reconciliation, main, duplicado — REVISADO
- **Bloque F** (ingestion live): main, prices, news, finbert_rt, silver_rt — REVISADO
- **Bloque G** (ingestion historical): 5 de 7 archivos usan Supabase, rotos — REVISADO
- **Bloque H** (ML sandbox): 6 de 7 archivos usan Supabase, rotos — REVISADO
- **Bloque I** (Docker/CI): 4 Dockerfiles, compose, 2 workflows, .dockerignore, requirements, pyproject — REVISADO
- **Bloque J** (YAMLs): ensemble, trading, tickers, 6 experiments, 1 backtest — REVISADO
- **Bloque K** (Tests): conftest, 3 test suites, test_all_services, verify_system, schema_fixes — REVISADO
- **Bloque L** (Placeholders): 2 workers, 5 services futuros — REVISADO

## Qué falta

- **Parte 2**: Arquitectura (flujo de datos, diagrama de dependencias, tablas PostgreSQL, ciclo de vida de señal, puntos de fallo)
- **Parte 3**: Azure (inventario servicios, configuración, guardrails de coste)

## Fixes aplicados en la auditoría (Fase 3c)

16 pendientes arreglados: ensemble weights + RF duplicado, golden_cross docstrings, CORS desde env var, retry con backoff en db.py, docstrings Supabase→PostgreSQL, merge conflict .dockerignore, CI branch main→master, supabase eliminado de pyproject.toml, psycopg2 añadido, volumen ingestion_live en compose, experiment names v1→v2, conftest .append() deprecated.

3 archivos pendientes de borrar manualmente: trading_engine_main.py (duplicado), debug_news.py (código muerto), tensor.py (redundante + Supabase).

## Decisiones de producto ya tomadas (Fase 6)

1. Pool de 500 tickers — usuarios eligen cuáles seguir
2. Guardrails personalizados por usuario POR ticker — cada combo user+ticker tiene su config
3. Usuarios pueden entrenar sus propios modelos eligiendo fechas train/test — modelos guardados en Blob Storage por user_id
4. Inferencia se ejecuta una vez por ticker para modelos compartidos. Usuarios con modelos propios tienen inferencia independiente
5. Squawks ML es app de ALERTAS, no de ejecución de órdenes

## Pendientes técnicos totales

- 16 Fase 3c: ARREGLADOS (13 en archivos, 3 borrados pendientes)
- 22 Fase 6: aplazados
- 11 mejoras de código: no urgentes
- Total: 49 puntos documentados

## Estadísticas del repo

- 121 archivos Python, 10.946 líneas, 366 funciones, 59 clases
- 13 YAMLs, 4 Dockerfiles, ~22 tablas PostgreSQL
- 6 modelos ML, 25 señales técnicas, 3 contenedores Docker

## Estilo de la auditoría

Para cada archivo: propósito en una frase, funciones con parámetros y retorno, dependencias, veredicto (✅ OK / ⚠️ Mejora / 🔴 Bug). Explico conceptos cuando el usuario pregunta.
