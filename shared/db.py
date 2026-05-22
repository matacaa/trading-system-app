"""
db.py
─────
Connection pool PostgreSQL compartido por todo el monorepo.
Reemplaza el antiguo cliente Supabase con conexión directa
a Azure PostgreSQL via psycopg2.

Compatible con PgBouncer (transaction mode, puerto 6432):
    - Si PgBouncer detectado, pool local se reduce (PgBouncer poolea)
    - No usa PREPARE ni SET session-level

Uso:
    from shared.db import query, execute, upsert

    # SELECT → lista de dicts
    rows = query("SELECT * FROM gold_trades WHERE ticker = %s", ["AAPL"])

    # INSERT/UPDATE → rowcount
    execute("INSERT INTO gold_logs (status) VALUES (%s)", ["ok"])

    # UPSERT con ON CONFLICT
    upsert("gold_signals", rows, conflict="ts,ticker,experiment_name")
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from functools import lru_cache

import psycopg2
import psycopg2.extras
import psycopg2.pool
import psycopg2.sql

from shared.config import cfg

# Whitelist de tablas permitidas para upsert (previene SQL injection)
_ALLOWED_TABLES = frozenset({
    "gold_squawks", "gold_signals", "gold_decisions", "gold_trades",
    "gold_logs", "gold_pipeline_timings",
    "raw_ohlcv_rt", "raw_news_rt", "silver_features_rt",
    "silver_model_registry", "silver_news_alpaca",
    "silver_predictions", "silver_metrics",
    "backtest_runs", "backtest_trades", "backtest_metrics",
    "ticker_universe", "guardrail_registry", "plan_config",
    "training_jobs", "model_type_registry", "user_credits",
    "users", "user_preferences", "config",
    "subscriptions", "stripe_events",
})

log = logging.getLogger(__name__)

# Errores transitorios de PostgreSQL que merecen retry
_TRANSIENT_ERRORS = (
    psycopg2.OperationalError,
    psycopg2.InterfaceError,
)
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # 0.5s, 1s, 2s


@lru_cache(maxsize=1)
def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Crea el pool una sola vez por proceso.

    Si PgBouncer está activo (puerto 6432), se reduce el pool local
    porque PgBouncer ya gestiona el pooling de conexiones.
    """
    if cfg.pgbouncer_enabled:
        minconn, maxconn = 1, 5
        log.info("PgBouncer detectado (puerto 6432) — pool reducido: %d-%d", minconn, maxconn)
    else:
        minconn, maxconn = 2, 10

    log.info("Inicializando pool PostgreSQL: %s", cfg.database_host)
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=minconn,
        maxconn=maxconn,
        dsn=cfg.database_url,
    )


@contextmanager
def get_conn():
    """Context manager que obtiene una conexión del pool con retry y backoff."""
    pool = _get_pool()
    last_err = None
    for attempt in range(_MAX_RETRIES):
        conn = None
        try:
            conn = pool.getconn()
            yield conn
            conn.commit()
            return
        except _TRANSIENT_ERRORS as e:
            last_err = e
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
                pool.putconn(conn, close=True)
                conn = None
            wait = _BACKOFF_BASE * (2 ** attempt)
            log.warning("DB transient error (attempt %d/%d), retry in %.1fs: %s",
                        attempt + 1, _MAX_RETRIES, wait, e)
            time.sleep(wait)
        except Exception:
            if conn is not None:
                conn.rollback()
                pool.putconn(conn)
                conn = None
            raise
        finally:
            if conn is not None:
                pool.putconn(conn)
    raise last_err  # type: ignore[misc]


def query(sql: str, params: list | tuple | None = None) -> list[dict]:
    """Ejecuta un SELECT y devuelve lista de dicts."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def query_one(sql: str, params: list | tuple | None = None) -> dict | None:
    """Ejecuta un SELECT y devuelve un solo dict o None."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: list | tuple | None = None) -> int:
    """Ejecuta INSERT/UPDATE/DELETE y devuelve rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def execute_many(sql: str, params_list: list[tuple]) -> int:
    """Ejecuta el mismo statement con múltiples sets de parámetros."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, params_list)
            return cur.rowcount


def upsert(
    table: str,
    rows: list[dict],
    conflict: str,
) -> int:
    """
    UPSERT genérico: INSERT ... ON CONFLICT (cols) DO UPDATE SET ...

    Usa psycopg2.sql.Identifier para tabla y columnas (previene SQL injection).

    Args:
        table: nombre de la tabla (debe estar en _ALLOWED_TABLES)
        rows: lista de dicts con las mismas keys
        conflict: columnas del constraint, e.g. "ts,ticker,experiment_name"

    Returns:
        número de filas afectadas
    """
    if not rows:
        return 0

    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Tabla '{table}' no permitida en upsert. Permitidas: {sorted(_ALLOWED_TABLES)}")

    columns = list(rows[0].keys())
    conflict_cols = [c.strip() for c in conflict.split(",")]
    update_cols = [c for c in columns if c not in conflict_cols]

    # Construir SQL con identificadores seguros
    tbl = psycopg2.sql.Identifier(table)
    col_ids = psycopg2.sql.SQL(", ").join(psycopg2.sql.Identifier(c) for c in columns)
    placeholders = psycopg2.sql.SQL(", ").join(psycopg2.sql.Placeholder() for _ in columns)
    conflict_ids = psycopg2.sql.SQL(", ").join(psycopg2.sql.Identifier(c) for c in conflict_cols)

    if update_cols:
        update_set = psycopg2.sql.SQL(", ").join(
            psycopg2.sql.SQL("{col} = EXCLUDED.{col}").format(
                col=psycopg2.sql.Identifier(c),
            )
            for c in update_cols
        )
        on_conflict = psycopg2.sql.SQL("DO UPDATE SET ") + update_set
    else:
        on_conflict = psycopg2.sql.SQL("DO NOTHING")

    stmt = psycopg2.sql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT ({conflict}) {action}"
    ).format(
        table=tbl,
        cols=col_ids,
        vals=placeholders,
        conflict=conflict_ids,
        action=on_conflict,
    )

    values_list = [tuple(row[c] for c in columns) for row in rows]

    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, stmt.as_string(cur), values_list)
            return cur.rowcount


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rows = query("SELECT tablename FROM pg_tables WHERE schemaname = 'public' LIMIT 10")
    print("Tablas en PostgreSQL:")
    for row in rows:
        print(f"  {row['tablename']}")
