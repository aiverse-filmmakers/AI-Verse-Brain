from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .errors import ScopeError, ValidationError

_SCOPE_RE = re.compile(r"^(operator|workspace:[a-z0-9][a-z0-9._-]{0,127})$")
_KINDS = {
    "intent", "practice", "gap", "opportunity", "initiative", "objective",
    "model_belief", "evaluation", "learning", "strategy_rule", "policy",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Scope:
    value: str

    def __post_init__(self) -> None:
        if not _SCOPE_RE.match(self.value):
            raise ScopeError(f"invalid scope: {self.value!r}")

    @property
    def is_operator(self) -> bool:
        return self.value == "operator"

    @property
    def workspace_id(self) -> Optional[str]:
        return None if self.is_operator else self.value.split(":", 1)[1]


@dataclass(frozen=True)
class EvidenceRef:
    ref: str
    evidence_class: str
    claim: Optional[str] = None
    observed_at: Optional[str] = None
    expires_at: Optional[str] = None
    scope: Optional[str] = None
    integrity: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in {
            "ref": self.ref,
            "evidence_class": self.evidence_class,
            "claim": self.claim,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "integrity": self.integrity,
        }.items() if v is not None}


@dataclass
class BrainObject:
    kind: str
    scope: Scope
    status: str
    payload: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: str = "1.0"
    revision: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    created_by: str = "brain"
    updated_by: str = "brain"
    source_refs: List[str] = field(default_factory=list)
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValidationError(f"unknown Brain object kind: {self.kind}")
        if not self.id or "/" in self.id or "\\" in self.id:
            raise ValidationError("object id must be non-empty and path-safe")
        if self.revision < 0:
            raise ValidationError("revision cannot be negative")
        if not isinstance(self.payload, dict):
            raise ValidationError("payload must be an object")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "kind": self.kind,
            "scope": self.scope.value,
            "status": self.status,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "source_refs": list(self.source_refs),
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrainObject":
        evidence = [EvidenceRef(**item) for item in data.get("evidence_refs", [])]
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            id=data["id"],
            kind=data["kind"],
            scope=Scope(data["scope"]),
            status=data["status"],
            revision=int(data.get("revision", 0)),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            created_by=data.get("created_by", "brain"),
            updated_by=data.get("updated_by", "brain"),
            source_refs=list(data.get("source_refs", [])),
            evidence_refs=evidence,
            supersedes=data.get("supersedes"),
            superseded_by=data.get("superseded_by"),
            payload=dict(data.get("payload", {})),
        )

    @classmethod
    def new(cls, kind: str, scope: str, status: str, payload: Dict[str, Any], *, created_by: str = "brain") -> "BrainObject":
        return cls(kind=kind, scope=Scope(scope), status=status, payload=payload, created_by=created_by, updated_by=created_by)
