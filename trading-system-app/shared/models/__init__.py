"""shared.models — modelos del ensemble y registry autodescubrible."""

from shared.models.base import BaseModel
from shared.models.registry import (
    all_model_names,
    get_model,
    list_models,
    load_model_from_path,
    register_model,
)

__all__ = [
    "BaseModel",
    "get_model",
    "all_model_names",
    "list_models",
    "register_model",
    "load_model_from_path",
]
