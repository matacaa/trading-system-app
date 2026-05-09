"""shared.models — modelos del ensemble y registry autodescubrible."""

from shared.models.base import BaseModel
from shared.models.registry import (
    get_model,
    all_model_names,
    list_models,
    register_model,
    load_model_from_path,
)

__all__ = [
    "BaseModel",
    "get_model",
    "all_model_names",
    "list_models",
    "register_model",
    "load_model_from_path",
]
