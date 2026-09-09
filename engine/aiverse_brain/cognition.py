from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from .authority import SELF_EVOLUTION_FORBIDDEN_FIELDS
from .errors import CognitionContractError
from .models import Scope, utc_now


class CognitionPurpose(str, Enum):
    ORIENT = "orient"
    GAP_ANALYSIS = "gap_analysis"
    OPPORTUNITY_DISCOVERY = "opportunity_discovery"
    OBJECTIVE_PLANNING = "objective_planning"
    REFLECTION = "reflection"
    STRATEGY_REVIEW = "strategy_review"
    EVALUATION = "evaluation"


ALLOWED_PROPOSAL_KINDS: Set[str] = {
    "gap", "opportunity", "initiative", "objective", "model_belief", "learning"
}

_TOP_LEVEL_CONTROL_KEYS = {
    "status", "scope", "kind", "revision", "created_at", "updated_at",
    "created_by", "updated_by", "policy", "action_policy", "authority_tier",
}


def _walk_forbidden(value: Any, forbidden: Set[str], path: str = "payload") -> Optional[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in forbidden:
                return f"{path}.{key}"
            found = _walk_forbidden(child, forbidden, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _walk_forbidden(child, forbidden, f"{path}[{index}]")
            if found:
                return found
    return None


@dataclass(frozen=True)
class CognitionRequest:
    purpose: CognitionPurpose
    scope: Scope
    context_refs: List[str]
    evidence_refs: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    output_contract: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "purpose": self.purpose.value,
            "scope": self.scope.value,
            "context_refs": list(self.context_refs),
            "evidence_refs": list(self.evidence_refs),
            "constraints": list(self.constraints),
            "output_contract": dict(self.output_contract),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CognitionProposal:
    request_id: str
    purpose: CognitionPurpose
    scope: Scope
    proposal_kind: str
    payload: Dict[str, Any]
    confidence: float
    source_model: str
    rationale: Optional[str] = None

    def __post_init__(self) -> None:
        if self.proposal_kind not in ALLOWED_PROPOSAL_KINDS:
            raise CognitionContractError(f"model may not propose canonical kind: {self.proposal_kind}")
        if not isinstance(self.payload, dict):
            raise CognitionContractError("proposal payload must be an object")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise CognitionContractError("proposal confidence must be normalized to [0,1]")
        if not self.source_model:
            raise CognitionContractError("source_model is required")
        top_level = sorted(set(self.payload) & _TOP_LEVEL_CONTROL_KEYS)
        if top_level:
            raise CognitionContractError("model proposal contains control-envelope fields: " + ", ".join(top_level))
        forbidden = _walk_forbidden(self.payload, set(SELF_EVOLUTION_FORBIDDEN_FIELDS))
        if forbidden:
            raise CognitionContractError(f"model proposal attempts privileged mutation at {forbidden}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "purpose": self.purpose.value,
            "scope": self.scope.value,
            "proposal_kind": self.proposal_kind,
            "payload": dict(self.payload),
            "confidence": float(self.confidence),
            "source_model": self.source_model,
            "rationale": self.rationale,
        }


def validate_proposal(request: CognitionRequest, proposal: CognitionProposal) -> None:
    if proposal.request_id != request.request_id:
        raise CognitionContractError("proposal request_id does not match cognition request")
    if proposal.scope != request.scope:
        raise CognitionContractError("proposal scope does not match cognition request")
    if proposal.purpose != request.purpose:
        raise CognitionContractError("proposal purpose does not match cognition request")
    permitted = request.output_contract.get("proposal_kinds")
    if permitted is not None and proposal.proposal_kind not in set(permitted):
        raise CognitionContractError(f"proposal kind {proposal.proposal_kind!r} is outside output contract")
