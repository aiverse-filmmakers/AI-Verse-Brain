from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .errors import ValidationError
from .write_router import WriteRoute, classify_write


@dataclass(frozen=True)
class OwnerWriteResult:
    classification: str
    route: str
    owner_ref: Optional[str]
    persisted: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification,
            "route": self.route,
            "owner_ref": self.owner_ref,
            "persisted": self.persisted,
        }


def route_durable_write(host: Any, classification: str, payload: Dict[str, Any], scope: str) -> OwnerWriteResult:
    """Route non-Brain durable state only through the canonical owner's host boundary."""
    if not isinstance(payload, dict):
        raise ValidationError("owner-routed payload must be an object")
    route = classify_write(classification)
    if route == WriteRoute.BRAIN_STATE:
        raise ValidationError("Brain-owned state must use Brain owner APIs, not host write_route")
    if route == WriteRoute.TRANSIENT:
        return OwnerWriteResult(classification, route.value, None, False)
    writer = getattr(host, "write_route", None)
    if not callable(writer):
        raise ValidationError(f"selected host does not expose owner-routed durable writes for {route.value}")
    owner_ref = writer(classification, payload, scope)
    if not isinstance(owner_ref, str) or not owner_ref.strip():
        raise ValidationError("canonical owner write did not return a stable owner reference/receipt")
    return OwnerWriteResult(classification, route.value, owner_ref.strip(), True)
