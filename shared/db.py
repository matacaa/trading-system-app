"""
db.py
─────
Connection pool PostgreSQL compartido por todo el monorepo.
Reemplaza el antiguo cliente Supabase con conexión directa
a Azure PostgreSQL via psycopg2.

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
from contextlib import contextmanager
from functools import lru_cache

import psycopg2
import psycopg2.pool
import psycopg2.extras

from shared.config import cfg

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Crea el pool una sola vez por proceso. Min 2, max 10 conexiones."""
    log.info("Inicializando pool PostgreSQL: %s", cfg.database_host)
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=cfg.database_url,
    )


@contextmanager
def get_conn():
    """Context manager que obtiene y devuelve una conexión del pool."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


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

    Args:
        table: nombre de la tabla
        rows: lista de dicts con las mismas keys
        conflict: columnas del constraint, e.g. "ts,ticker,experiment_name"

    Returns:
        número de filas afectadas
    """
    if not rows:
        return 0

    columns = list(rows[0].keys())
    conflict_cols = [c.strip() for c in conflict.split(",")]
    update_cols = [c for c in columns if c not in conflict_cols]

    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    sql = f"""
        INSERT INTO {table} ({col_list})
        VALUES ({placeholders})
        ON CONFLICT ({conflict})
        {"DO UPDATE SET " + update_set if update_set else "DO NOTHING"}
    """

    values_list = [tuple(row[c] for c in columns) for row in rows]

    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, values_list)
            return cur.rowcount


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rows = query("SELECT tablename FROM pg_tables WHERE schemaname = 'public' LIMIT 10")
    print("Tablas en PostgreSQL:")
    for row in rows:
        print(f"  {row['tablename']}")
