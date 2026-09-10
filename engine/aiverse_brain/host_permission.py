from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from .errors import PermissionDenied, ValidationError


HOST_PERMISSION_DECISIONS = {"allow", "approval_required", "deny"}
_REQUIRED_FIELDS = {
    "decision",
    "request_fingerprint",
    "scope",
    "action_class",
    "source",
    "reason",
}


@dataclass(frozen=True)
class HostPermissionDecision:
    """A restrictive host-side permission decision for one exact action request.

    Host permission is an independent lower/outer bound on Brain authority.  It
    can require approval or deny an action, but it can never make an action more
    permissive than Brain's own effective policy.
    """

    decision: str
    request_fingerprint: str
    scope: str
    action_class: str
    source: str
    reason: str

    @classmethod
    def from_result(
        cls,
        result: Mapping[str, Any],
        *,
        expected_fingerprint: str,
        expected_scope: str,
        expected_action_class: str,
    ) -> "HostPermissionDecision":
        if not isinstance(result, Mapping):
            raise ValidationError("host permission result must be an object")
        if set(result) != _REQUIRED_FIELDS:
            raise ValidationError("host permission result has missing or unknown fields")

        values: Dict[str, str] = {}
        for field in _REQUIRED_FIELDS:
            value = result.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"host permission {field} must be a non-empty string")
            values[field] = value.strip()

        if values["decision"] not in HOST_PERMISSION_DECISIONS:
            raise ValidationError(f"unknown host permission decision: {values['decision']}")
        if values["request_fingerprint"] != expected_fingerprint:
            raise PermissionDenied("host permission decision does not match the exact action request")
        if values["scope"] != expected_scope:
            raise PermissionDenied("host permission scope does not match action request")
        if values["action_class"] != expected_action_class:
            raise PermissionDenied("host permission action class does not match action request")

        return cls(
            decision=values["decision"],
            request_fingerprint=values["request_fingerprint"],
            scope=values["scope"],
            action_class=values["action_class"],
            source=values["source"],
            reason=values["reason"],
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "decision": self.decision,
            "request_fingerprint": self.request_fingerprint,
            "scope": self.scope,
            "action_class": self.action_class,
            "source": self.source,
            "reason": self.reason,
        }


def permission_request(action: Any) -> Dict[str, Any]:
    """Build the immutable request envelope passed to a host permission source."""

    payload = action.to_dict()
    payload["request_fingerprint"] = action.fingerprint()
    return payload
