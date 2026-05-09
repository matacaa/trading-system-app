"""
db.py
─────
Cliente Supabase singleton compartido por todo el monorepo.
Resuelve el antipatrón de crear un cliente nuevo en cada función
(F-26, F-33, F-43, F-63 del informe de Fase 2).

Uso:
    from shared.db import sb
    
    resp = sb.table("gold_trades").select("*").execute()
"""

from __future__ import annotations

import logging
from functools import lru_cache

from supabase import Client, create_client

from shared.config import cfg

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_client() -> Client:
    """Crea el cliente Supabase una sola vez por proceso."""
    log.debug(f"Inicializando cliente Supabase: {cfg.supabase_url}")
    return create_client(cfg.supabase_url, cfg.supabase_key)


# Exponemos `sb` como instancia lista para usar
sb: Client = _get_client()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    # Test básico: leer 1 fila de symbols
    resp = sb.table("symbols").select("ticker,name").limit(3).execute()
    print("Respuesta de Supabase:")
    for row in resp.data:
        print(f"  {row}")
