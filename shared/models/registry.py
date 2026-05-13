"""
registry.py
───────────
Registro automático de modelos con decorador @register_model.

Para añadir un modelo nuevo:
    1. Crea un archivo en sklearn_models/ o pytorch_models/
    2. Hereda de BaseModel y define name, model_type, requires_gpu
    3. Añade @register_model encima de la clase
    4. Push a GitHub → el modelo aparece en la app automáticamente

Uso:
    from shared.models.registry import get_model, list_models, register_model

    model = get_model("xgboost", task="classification", params={"n_estimators": 200})
    available = list_models()
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from shared.db import query_one
from shared.models.base import BaseModel

log = logging.getLogger(__name__)

# ─── Registro global ──────────────────────────────────────────────
MODEL_REGISTRY: dict[str, type[BaseModel]] = {}


def register_model(cls: type[BaseModel]) -> type[BaseModel]:
    """Decorador que registra una clase de modelo en el registro global.

    Uso:
        @register_model
        class WaveNetModel(BaseModel):
            name = "wavenet"
            model_type = "deep_learning"
            requires_gpu = True
            ...
    """
    if not cls.name:
        raise ValueError(
            f"{cls.__name__} no tiene 'name' definido. "
            f"Añade name = 'mi_modelo' como atributo de clase."
        )
    if cls.name in MODEL_REGISTRY:
        log.warning(
            f"Modelo '{cls.name}' ya registrado ({MODEL_REGISTRY[cls.name].__name__}). "
            f"Sobrescribiendo con {cls.__name__}."
        )
    MODEL_REGISTRY[cls.name] = cls
    log.debug(f"Modelo registrado: {cls.name} ({cls.__name__})")
    return cls


def _auto_discover() -> None:
    """Importa todos los módulos en sklearn_models/ y pytorch_models/.

    Esto dispara los decoradores @register_model de cada clase,
    registrándolas en MODEL_REGISTRY sin necesidad de imports manuales.
    """
    if MODEL_REGISTRY:
        return  # ya descubiertos

    models_dir = Path(__file__).parent
    for subdir in ["sklearn_models", "pytorch_models"]:
        package_path = models_dir / subdir
        if not package_path.is_dir():
            continue
        package_name = f"shared.models.{subdir}"
        for _, module_name, _ in pkgutil.iter_modules([str(package_path)]):
            if module_name.startswith("_"):
                continue
            try:
                importlib.import_module(f"{package_name}.{module_name}")
            except ImportError as e:
                log.warning(f"No se pudo importar {package_name}.{module_name}: {e}")


# ─── API pública ──────────────────────────────────────────────────

def all_model_names() -> list[str]:
    """Lista de todos los nombres de modelo registrados."""
    _auto_discover()
    return list(MODEL_REGISTRY.keys())


def list_models() -> list[dict]:
    """Devuelve metadata de todos los modelos registrados.

    Usado por GET /api/models/available para que la app muestre
    los modelos disponibles sin hardcodear nada en el frontend.
    """
    _auto_discover()
    return [
        {
            "name": cls.name,
            "model_type": cls.model_type,
            "requires_gpu": cls.requires_gpu,
            "class": cls.__name__,
        }
        for cls in MODEL_REGISTRY.values()
    ]


def get_model(
    model_name: str,
    task: str = "classification",
    params: dict | None = None,
    check_library: bool = True,
    **extra_kwargs,
) -> BaseModel:
    """
    Instancia el modelo correcto según su nombre.

    1. Auto-descubre modelos si no se ha hecho aún
    2. (Opcional) Verifica en silver_model_library de Supabase
    3. Combina default_params con params recibidos (params gana)
    4. Instancia la clase del modelo

    Args:
        model_name:     nombre del modelo (xgboost, lstm, wavenet, etc.)
        task:           'classification' o 'regression'
        params:         hiperparámetros del yaml (prioridad sobre defaults)
        check_library:  si True, consulta silver_model_library en Supabase
        **extra_kwargs: kwargs adicionales pasados al constructor

    Returns:
        Instancia del modelo lista para entrenar
    """
    _auto_discover()
    params = params or {}

    if model_name not in MODEL_REGISTRY:
        raise ValueError(
            f"Modelo '{model_name}' no reconocido. "
            f"Disponibles: {all_model_names()}"
        )

    # ─── Consultar silver_model_library (opcional) ──────────────
    default_params: dict = {}

    if check_library:
        try:
            library_entry = query_one(
                """SELECT model_name, model_type, active, default_params
                   FROM silver_model_library WHERE model_name = %s""",
                [model_name],
            )
        except Exception as e:
            log.warning(
                f"No se pudo consultar silver_model_library para '{model_name}': {e}. "
                f"Continuando sin defaults de PostgreSQL."
            )
            library_entry = None

        if library_entry:
            if not library_entry.get("active", False):
                raise ValueError(
                    f"Modelo '{model_name}' está desactivado en silver_model_library. "
                    f"Actívalo en PostgreSQL o usa check_library=False."
                )
            default_params = library_entry.get("default_params") or {}

    # ─── Combinar params: defaults + yaml (yaml gana) ──────────
    final_params = {**default_params, **params}

    overridden = set(default_params.keys()) & set(params.keys())
    if overridden:
        for key in sorted(overridden):
            log.info(
                f"  Param '{key}': default={default_params[key]} → yaml={params[key]}"
            )

    log.info(f"Modelo: {model_name} | Task: {task} | Params: {final_params}")

    # ─── Instanciar ─────────────────────────────────────────────
    model_class = MODEL_REGISTRY[model_name]
    return model_class(task=task, **final_params, **extra_kwargs)


def load_model_from_path(
    model_name: str,
    file_path,
    task: str = "classification",
) -> BaseModel | None:
    """Carga un modelo entrenado desde disco usando el registry.

    Reemplaza el if/elif hardcodeado de inference._load_model().

    Args:
        model_name: nombre del modelo (debe estar registrado)
        file_path:  path al fichero del modelo (.pkl, .pt, etc.)
        task:       'classification' o 'regression'

    Returns:
        Instancia del modelo cargado, o None si falla
    """
    _auto_discover()

    if model_name not in MODEL_REGISTRY:
        log.warning(f"Modelo no reconocido: {model_name}")
        return None

    try:
        model_class = MODEL_REGISTRY[model_name]
        return model_class.load(file_path, task=task)
    except Exception as e:
        log.error(f"Error cargando {model_name} desde {file_path}: {e}")
        return None
