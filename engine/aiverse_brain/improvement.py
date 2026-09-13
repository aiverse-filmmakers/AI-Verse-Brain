from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .authority import AuthorityTier
from .errors import AuthorityError, ValidationError
from .models import BrainObject, EvidenceRef, utc_now
from .owner_write import route_durable_write


@dataclass(frozen=True)
class ImprovementCandidateEnvelope:
    candidate_id: str
    scope: str
    suggested_owner: str
    kind: str
    summary: str
    target_skill_id: Optional[str]
    target_generation: Optional[str]
    target_digest: Optional[str]
    evidence_refs: List[str]
    success_signal: List[str]
    failure_signal: List[str]
    risk: str
    confidence: float
    evaluation_criteria: List[str]
    requested_operation: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id, "scope": self.scope,
            "suggested_owner": self.suggested_owner, "kind": self.kind,
            "summary": self.summary, "target_skill_id": self.target_skill_id,
            "target_generation": self.target_generation, "target_digest": self.target_digest,
            "evidence_refs": list(self.evidence_refs),
            "success_signal": list(self.success_signal), "failure_signal": list(self.failure_signal),
            "risk": self.risk, "confidence": self.confidence,
            "evaluation_criteria": list(self.evaluation_criteria),
            "requested_operation": self.requested_operation, "created_at": self.created_at,
        }


class ImprovementCandidateService:
    """Brain-owned evaluation output. Skill bytes and proposal promotion remain Skills-owned."""

    OWNER_CLASSIFICATIONS = {
        "skills": "repeatable_execution", "memory": "historical_experience",
        "data": "structured_operational_state", "brain": "learning_candidate",
        "os": "reusable_knowledge", "automation": "automation_candidate",
        "bot": "bot_candidate", "none": "transient",
    }
    KINDS = {"create", "repair", "consolidate", "archive-review", "memory"}
    RISKS = {"low", "medium", "high"}

    def __init__(self, controller: Any):
        self.controller = controller

    def create(
        self, scope: str, *, suggested_owner: str, kind: str, summary: str,
        evidence_refs: List[EvidenceRef], risk: str, confidence: float,
        success_signal: Optional[List[str]] = None, failure_signal: Optional[List[str]] = None,
        evaluation_criteria: Optional[List[str]] = None, target_skill_id: Optional[str] = None,
        target_generation: Optional[str] = None, target_digest: Optional[str] = None,
        requested_operation: Optional[str] = None,
        source: AuthorityTier = AuthorityTier.VERIFIED_EVIDENCE,
        actor: str = "brain:evaluator",
    ) -> BrainObject:
        if suggested_owner not in self.OWNER_CLASSIFICATIONS:
            raise ValidationError(f"unknown improvement owner: {suggested_owner}")
        if kind not in self.KINDS: raise ValidationError(f"unknown improvement candidate kind: {kind}")
        if risk not in self.RISKS: raise ValidationError(f"unknown improvement risk: {risk}")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            raise ValidationError("improvement confidence must be normalized to [0,1]")
        if not isinstance(summary, str) or not summary.strip(): raise ValidationError("improvement summary is required")
        if not evidence_refs: raise ValidationError("improvement candidate requires evidence references")
        if source > AuthorityTier.VERIFIED_EVIDENCE:
            raise AuthorityError("durable improvement candidate requires verified evidence or stronger authority")
        if kind == "repair" and not all((target_skill_id, target_generation, target_digest)):
            raise ValidationError("Skill repair must bind exact target Skill generation and digest")
        envelope = ImprovementCandidateEnvelope(
            "learn_" + uuid4().hex, scope, suggested_owner, kind, summary.strip(),
            target_skill_id, target_generation, target_digest,
            [item.ref for item in evidence_refs], list(success_signal or []), list(failure_signal or []),
            risk, float(confidence), list(evaluation_criteria or []), requested_operation or kind, utc_now(),
        )
        return self.controller.create(
            "learning_candidate", scope, "CANDIDATE", envelope.to_dict(),
            source=source, actor=actor, evidence_refs=list(evidence_refs),
        )

    def from_learning(
        self, scope: str, learning_id: str, *, suggested_owner: str = "skills",
        kind: str = "create", risk: str = "low", confidence: float = 0.7,
        target_skill_id: Optional[str] = None, target_generation: Optional[str] = None,
        target_digest: Optional[str] = None, evaluation_criteria: Optional[List[str]] = None,
        actor: str = "brain:evaluator",
    ) -> BrainObject:
        learning = self.controller.store.load("learning", scope, learning_id)
        if learning.status not in {"PATTERN", "REFLECTION", "VALIDATED_LEARNING", "STRATEGY_CANDIDATE", "PROMOTED"}:
            raise ValidationError("learning is not mature enough to emit a reusable improvement candidate")
        return self.create(
            scope, suggested_owner=suggested_owner, kind=kind,
            summary=str(learning.payload["statement"]), evidence_refs=list(learning.evidence_refs),
            risk=risk, confidence=confidence, target_skill_id=target_skill_id,
            target_generation=target_generation, target_digest=target_digest,
            evaluation_criteria=evaluation_criteria, actor=actor,
        )

    def route(self, scope: str, candidate_id: str, host: Any, *, actor: str = "brain:write-router") -> Dict[str, Any]:
        obj = self.controller.store.load("learning_candidate", scope, candidate_id)
        if obj.status != "CANDIDATE": raise ValidationError(f"candidate is not routable from {obj.status}")
        owner = str(obj.payload["suggested_owner"])
        classification = self.OWNER_CLASSIFICATIONS[owner]
        if classification == "learning_candidate":
            return {"candidate": obj.to_dict(), "owner_ref": f"brain:learning_candidate:{obj.id}", "routed": False}
        result = route_durable_write(host, classification, obj.payload, scope)
        expected = obj.revision
        obj.status = "ROUTED" if result.persisted else "RETIRED"
        obj.payload["owner_route"] = result.to_dict()
        obj.updated_by = actor
        saved = self.controller.store.save(obj, expected_revision=expected)
        return {"candidate": saved.to_dict(), "owner_ref": result.owner_ref, "routed": result.persisted}
