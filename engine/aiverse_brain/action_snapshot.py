from __future__ import annotations

import math
from types import MappingProxyType
from typing import Any, Dict, Mapping

from .errors import ValidationError


def freeze_json(value: Any, *, path: str = "parameters") -> Any:
    """Deep-copy JSON-like action data into immutable containers."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        copied: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} object keys must be strings")
            copied[key] = freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item, path=f"{path}[]") for item in value)
    raise ValidationError(f"{path} contains unsupported value type: {type(value).__name__}")


def thaw_json(value: Any) -> Any:
    """Return a detached mutable JSON-compatible copy for serialization/host dispatch."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value
