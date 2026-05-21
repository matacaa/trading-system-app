"""
shared/cache.py
───────────────
Cache Redis para datos de acceso frecuente.

Si REDIS_URL no está configurado, opera como passthrough (sin cache).
Esto permite desarrollo local sin Redis.

Datos cacheados:
    - plan_config (TTL 5min): configuración de planes por tier
    - ticker_universe (TTL 5min): lista de tickers disponibles
    - system_scores (TTL 30s): scores del sistema por ticker
    - user_preferences (TTL 2min): preferencias del usuario

Uso:
    from shared.cache import cache

    # Guardar
    cache.set("plan_config:pro", data, ttl=300)

    # Leer
    data = cache.get("plan_config:pro")

    # Invalidar
    cache.delete("plan_config:pro")

    # Pattern: cache-aside con fallback a DB
    data = cache.get(key)
    if data is None:
        data = query_from_db(...)
        cache.set(key, data, ttl=300)
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

_redis_client = None
_redis_available = False


def _get_redis():
    """Inicializa la conexión Redis (lazy, una sola vez)."""
    global _redis_client, _redis_available

    if _redis_client is not None:
        return _redis_client

    from shared.config import cfg

    if not cfg.redis_url:
        log.info("REDIS_URL no configurado — cache desactivado (passthrough)")
        _redis_available = False
        return None

    try:
        import redis

        _redis_client = redis.from_url(
            cfg.redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=True,
        )
        # Test de conexión
        _redis_client.ping()
        _redis_available = True
        log.info("Redis conectado: %s", cfg.redis_url.split("@")[-1] if "@" in cfg.redis_url else "localhost")
        return _redis_client

    except Exception as e:
        log.warning("Redis no disponible — cache desactivado: %s", e)
        _redis_available = False
        _redis_client = None
        return None


class Cache:
    """Interfaz de cache Redis con fallback a no-op."""

    # TTLs por defecto (segundos)
    TTL_PLAN_CONFIG = 300       # 5 min
    TTL_TICKER_UNIVERSE = 300   # 5 min
    TTL_USER_PREFERENCES = 120  # 2 min
    TTL_SYSTEM_SCORES = 30      # 30 seg
    TTL_DEFAULT = 60            # 1 min

    def get(self, key: str) -> dict | list | str | None:
        """Lee un valor del cache. Devuelve None si no existe o Redis no disponible."""
        client = _get_redis()
        if client is None:
            return None

        try:
            raw = client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
        except Exception as e:
            log.debug("Cache get error (%s): %s", key, e)
            return None

    def set(self, key: str, value, ttl: int | None = None) -> bool:
        """Guarda un valor en el cache con TTL opcional."""
        client = _get_redis()
        if client is None:
            return False

        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                client.setex(key, ttl, serialized)
            else:
                client.setex(key, self.TTL_DEFAULT, serialized)
            return True
        except Exception as e:
            log.debug("Cache set error (%s): %s", key, e)
            return False

    def delete(self, key: str) -> bool:
        """Elimina un valor del cache."""
        client = _get_redis()
        if client is None:
            return False

        try:
            client.delete(key)
            return True
        except Exception as e:
            log.debug("Cache delete error (%s): %s", key, e)
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Elimina todas las keys que coincidan con el patrón (e.g. 'plan_config:*')."""
        client = _get_redis()
        if client is None:
            return 0

        try:
            keys = list(client.scan_iter(match=pattern, count=100))
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            log.debug("Cache delete_pattern error (%s): %s", pattern, e)
            return 0

    def is_available(self) -> bool:
        """Devuelve True si Redis está conectado y respondiendo."""
        client = _get_redis()
        if client is None:
            return False
        try:
            return client.ping()
        except Exception:
            return False

    # ── Helpers de alto nivel ──────────────────────────────────────────

    def get_plan_config(self, tier: str) -> dict | None:
        """Lee plan_config de cache o None."""
        return self.get(f"plan_config:{tier}")

    def set_plan_config(self, tier: str, config: dict) -> bool:
        """Cachea plan_config."""
        return self.set(f"plan_config:{tier}", config, ttl=self.TTL_PLAN_CONFIG)

    def get_ticker_universe(self) -> list | None:
        """Lee ticker_universe de cache o None."""
        return self.get("ticker_universe:all")

    def set_ticker_universe(self, tickers: list) -> bool:
        """Cachea ticker_universe."""
        return self.set("ticker_universe:all", tickers, ttl=self.TTL_TICKER_UNIVERSE)

    def get_system_score(self, ticker: str) -> dict | None:
        """Lee score del sistema para un ticker."""
        return self.get(f"system_score:{ticker}")

    def set_system_score(self, ticker: str, score_data: dict) -> bool:
        """Cachea score del sistema (TTL corto)."""
        return self.set(f"system_score:{ticker}", score_data, ttl=self.TTL_SYSTEM_SCORES)

    def get_user_preferences(self, user_id: str) -> dict | None:
        """Lee preferencias de usuario de cache."""
        return self.get(f"user_prefs:{user_id}")

    def set_user_preferences(self, user_id: str, prefs: dict) -> bool:
        """Cachea preferencias de usuario."""
        return self.set(f"user_prefs:{user_id}", prefs, ttl=self.TTL_USER_PREFERENCES)

    def invalidate_user(self, user_id: str) -> int:
        """Invalida todo el cache de un usuario."""
        return self.delete_pattern(f"user_prefs:{user_id}*")


# Singleton
cache = Cache()
