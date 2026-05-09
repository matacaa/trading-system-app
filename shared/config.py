"""
config.py
─────────
Configuración centralizada del sistema.
Lee .env una sola vez y expone un objeto `cfg` singleton.

Uso:
    from shared.config import cfg
    
    client = create_client(cfg.supabase_url, cfg.supabase_key)
    models_dir = cfg.models_dir
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


# Cargar .env desde la raíz del repo (auto-detectado)
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")


class _Config:
    """Singleton de configuración del sistema."""

    def __init__(self) -> None:
        # ─── Paths ─────────────────────────────────
        self.repo_root: Path = _REPO_ROOT
        self.data_dir: Path = self.repo_root / "data"
        self.tensors_dir: Path = self.data_dir / "tensors"
        self.models_dir: Path = self.data_dir / "models"
        self.logs_dir: Path = self.data_dir / "logs"
        self.config_dir: Path = self.repo_root / "config"

        # Crear dirs si no existen
        for d in (self.data_dir, self.tensors_dir, self.models_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        # ─── Supabase ──────────────────────────────
        self.supabase_url: str = self._require("SUPABASE_URL")
        self.supabase_key: str = self._require("SUPABASE_KEY")

        # ─── Alpaca ────────────────────────────────
        self.alpaca_api_key: str = self._require("ALPACA_API_KEY")
        self.alpaca_secret_key: str = self._require("ALPACA_SECRET_KEY")
        self.alpaca_base_url: str = os.getenv(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2"
        )
        self.alpaca_paper: bool = "paper" in self.alpaca_base_url

        # ── Protección contra modo live accidental ─────
        if not self.alpaca_paper:
            import logging
            _log = logging.getLogger(__name__)
            _log.critical(
                "⚠️  ALPACA_BASE_URL NO apunta a paper trading. "
                "Cambia a https://paper-api.alpaca.markets/v2 o "
                "establece la variable ALLOW_LIVE_TRADING=true para continuar."
            )
            if not os.getenv("ALLOW_LIVE_TRADING", "").lower() == "true":
                raise RuntimeError(
                    "ALPACA_BASE_URL apunta a live trading. "
                    "Esto es probablemente un error. Si es intencional, "
                    "establece ALLOW_LIVE_TRADING=true en tu .env"
                )

        # ─── HuggingFace ───────────────────────────
        self.huggingface_token: str = self._require("HUGGINGFACE_TOKEN")

        # ─── Batch sizes / límites ─────────────────
        self.batch_insert: int = int(os.getenv("BATCH_INSERT", "500"))

    @staticmethod
    def _require(key: str) -> str:
        """Exige que la variable exista y no esté vacía."""
        val = os.getenv(key, "").strip()
        if not val:
            raise RuntimeError(
                f"Variable de entorno requerida no encontrada o vacía: {key}. "
                f"Revisa tu fichero .env en {_REPO_ROOT / '.env'}"
            )
        return val

    def __repr__(self) -> str:
        return (
            f"_Config("
            f"supabase={self.supabase_url}, "
            f"alpaca_paper={self.alpaca_paper}, "
            f"repo_root={self.repo_root}"
            f")"
        )


@lru_cache(maxsize=1)
def _get_cfg() -> _Config:
    """Factory con caché. Garantiza un único Config por proceso."""
    return _Config()


# Exponemos cfg como instancia accesible
cfg = _get_cfg()


if __name__ == "__main__":
    print(cfg)
    print(f"  data_dir:    {cfg.data_dir}")
    print(f"  models_dir:  {cfg.models_dir}")
    print(f"  tensors_dir: {cfg.tensors_dir}")
