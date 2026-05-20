"""
shared/blob_storage.py
──────────────────────
Gestión de modelos ML en Azure Blob Storage.
Subida, descarga (con cache local), eliminación y listado.

Uso:
    from shared.blob_storage import upload_model, download_model, delete_model

Requiere env vars:
    AZURE_STORAGE_CONN_STR              — Connection string del Storage Account
    AZURE_STORAGE_MODELS_CONTAINER      — Nombre del contenedor (default: "models")

Estructura Blob:
    models/
      system/{experiment_name}/model.pt|.pkl
      users/{user_id}/{ticker}/{model_name}/model.pt|.pkl
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

STORAGE_CONN_STR = os.getenv("AZURE_STORAGE_CONN_STR", "")
MODELS_CONTAINER = os.getenv("AZURE_STORAGE_MODELS_CONTAINER", "models")
LOCAL_CACHE_DIR = Path("/tmp/models")


def _get_container_client():
    """Obtiene el container client para el contenedor de modelos."""
    from azure.storage.blob import BlobServiceClient

    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
    return blob_service.get_container_client(MODELS_CONTAINER)


def _cache_path(blob_path: str) -> Path:
    """Genera un path local único para cachear un blob."""
    # Hash del blob_path para evitar colisiones y caracteres raros
    h = hashlib.md5(blob_path.encode()).hexdigest()[:12]
    ext = Path(blob_path).suffix or ".bin"
    return LOCAL_CACHE_DIR / f"{h}{ext}"


# ── Upload ────────────────────────────────────────────────────────────────────


def upload_model(
    model_bytes: bytes,
    blob_path: str,
) -> str:
    """
    Sube un modelo serializado a Blob Storage.

    Args:
        model_bytes: bytes del modelo (.pkl o .pt)
        blob_path:   ruta dentro del contenedor, ej:
                     "system/aapl_lgbm_v1/model.pkl"
                     "users/{user_id}/AAPL/my_model/model.pt"

    Returns:
        blob_path tal cual (para guardar en silver_model_registry.blob_path)
    """
    if not STORAGE_CONN_STR:
        log.warning("AZURE_STORAGE_CONN_STR no configurado — upload desactivado")
        return blob_path

    try:
        from azure.storage.blob import ContentSettings

        container = _get_container_client()
        blob_client = container.get_blob_client(blob_path)
        blob_client.upload_blob(
            model_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/octet-stream"),
        )
        log.info("Modelo subido a Blob Storage: %s (%d bytes)", blob_path, len(model_bytes))
        return blob_path
    except Exception as e:
        log.error("Error subiendo modelo a Blob Storage: %s", e)
        raise


def upload_model_file(
    local_path: str | Path,
    blob_path: str,
) -> str:
    """Sube un archivo local a Blob Storage."""
    local_path = Path(local_path)
    return upload_model(local_path.read_bytes(), blob_path)


# ── Download ──────────────────────────────────────────────────────────────────


def download_model(blob_path: str, force: bool = False) -> bytes:
    """
    Descarga un modelo de Blob Storage con cache local.

    Args:
        blob_path: ruta dentro del contenedor
        force:     si True, ignora cache y descarga siempre

    Returns:
        bytes del modelo
    """
    if not STORAGE_CONN_STR:
        raise RuntimeError("AZURE_STORAGE_CONN_STR no configurado")

    # Check cache
    cached = _cache_path(blob_path)
    if not force and cached.exists():
        log.debug("Modelo cargado de cache local: %s", cached)
        return cached.read_bytes()

    try:
        container = _get_container_client()
        blob_client = container.get_blob_client(blob_path)
        data = blob_client.download_blob().readall()

        # Write to cache
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
        log.info("Modelo descargado de Blob Storage: %s (%d bytes)", blob_path, len(data))
        return data
    except Exception as e:
        log.error("Error descargando modelo de Blob Storage: %s", e)
        raise


def download_model_to_file(blob_path: str, local_path: str | Path) -> Path:
    """Descarga un modelo y lo guarda en un archivo local."""
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    data = download_model(blob_path)
    local_path.write_bytes(data)
    return local_path


def ensure_local(blob_path: str, local_dir: str | Path = LOCAL_CACHE_DIR) -> Path:
    """
    Asegura que el modelo está disponible localmente.
    Si ya está en cache, devuelve el path. Si no, lo descarga.

    Usado por inference.py para cargar modelos.
    """
    cached = _cache_path(blob_path)
    if cached.exists():
        return cached
    download_model(blob_path)
    return cached


# ── Delete ────────────────────────────────────────────────────────────────────


def delete_model(blob_path: str) -> bool:
    """
    Elimina un modelo de Blob Storage y de la cache local.

    Returns:
        True si se eliminó correctamente
    """
    if not STORAGE_CONN_STR:
        log.warning("AZURE_STORAGE_CONN_STR no configurado — delete desactivado")
        return False

    try:
        container = _get_container_client()
        blob_client = container.get_blob_client(blob_path)
        blob_client.delete_blob()
        log.info("Modelo eliminado de Blob Storage: %s", blob_path)
    except Exception as e:
        log.error("Error eliminando modelo de Blob Storage: %s", e)
        return False

    # Clean cache
    cached = _cache_path(blob_path)
    if cached.exists():
        cached.unlink()

    return True


# ── List ──────────────────────────────────────────────────────────────────────


def list_models(prefix: str = "") -> list[str]:
    """
    Lista modelos en Blob Storage con un prefijo.

    Args:
        prefix: ej. "system/", "users/{user_id}/AAPL/"

    Returns:
        lista de blob_paths
    """
    if not STORAGE_CONN_STR:
        return []

    try:
        container = _get_container_client()
        blobs = container.list_blobs(name_starts_with=prefix)
        return [b.name for b in blobs]
    except Exception as e:
        log.error("Error listando modelos en Blob Storage: %s", e)
        return []


def build_blob_path(
    experiment_name: str,
    ext: str = ".pkl",
    user_id: str | None = None,
    ticker: str | None = None,
) -> str:
    """
    Construye el blob_path para un modelo.

    Sistema: system/{experiment_name}/model.ext
    Custom:  users/{user_id}/{ticker}/{experiment_name}/model.ext
    """
    if user_id and ticker:
        return f"users/{user_id}/{ticker}/{experiment_name}/model{ext}"
    return f"system/{experiment_name}/model{ext}"
