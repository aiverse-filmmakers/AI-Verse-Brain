from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, TYPE_CHECKING

from .authority import AuthorityTier
from .errors import EvaluationError, ValidationError
from .models import BrainObject, EvidenceRef

if TYPE_CHECKING:
    from .controller import BrainController


class Independence(str, Enum):
    SAME_CONTEXT = "same_context"
    FRESH_CONTEXT = "fresh_context"
    INDEPENDENT_MODEL = "independent_model"
    EXTERNAL_AUTHORITATIVE = "external_authoritative"


_LEVEL_RANK = {"V0": 0, "V1": 1, "V2": 2, "V3": 3}
_INDEPENDENCE_RANK = {
    Independence.SAME_CONTEXT: 0,
    Independence.FRESH_CONTEXT: 1,
    Independence.INDEPENDENT_MODEL: 2,
    Independence.EXTERNAL_AUTHORITATIVE: 3,
}
_CRITERION_STATUSES = {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}
_STRONG_EVIDENCE = {
    "USER_CONFIRMATION", "CANONICAL_STATE", "DIRECT_MEASUREMENT",
    "AUTHORITATIVE_EXTERNAL", "INDEPENDENT_EVALUATION",
}


@dataclass(frozen=True)
class CriterionVerdict:
    criterion_id: str
    status: str
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    rationale: Optional[str] = None

    def validate(self) -> None:
        if not self.criterion_id:
            raise EvaluationError("criterion verdict id is required")
        if self.status not in _CRITERION_STATUSES:
            raise EvaluationError(f"invalid criterion verdict status: {self.status}")
        if self.status == "passed" and not self.evidence_refs:
            raise EvaluationError("passed criterion verdict requires evidence")

    def to_dict(self) -> Dict[str, object]:
        result: Dict[str, object] = {
            "criterion_id": self.criterion_id,
            "status": self.status,
            "evidence_refs": [item.ref for item in self.evidence_refs],
        }
        if self.rationale is not None:
            result["rationale"] = self.rationale
        return result


@dataclass(frozen=True)
class EvaluationResult:
    target_ref: str
    verification_level: str
    independence: Independence
    verdicts: List[CriterionVerdict]
    evaluator_id: str
    builder_context_id: Optional[str] = None
    evaluator_context_id: Optional[str] = None
    notes: Optional[str] = None

    def validate(self) -> None:
        if self.verification_level not in _LEVEL_RANK:
            raise EvaluationError(f"unknown verification level: {self.verification_level}")
        if not self.target_ref or not self.evaluator_id:
            raise EvaluationError("target_ref and evaluator_id are required")
        ids = [item.criterion_id for item in self.verdicts]
        if len(ids) != len(set(ids)):
            raise EvaluationError("criterion verdict ids must be unique")
        level = _LEVEL_RANK[self.verification_level]
        for verdict in self.verdicts:
            verdict.validate()
            if verdict.status == "passed" and level >= 1:
                if all(item.evidence_class == "MODEL_INFERENCE" for item in verdict.evidence_refs):
                    raise EvaluationError("V1+ criterion cannot pass on model inference alone")
            if verdict.status == "passed" and level >= 2:
                if not any(item.evidence_class in _STRONG_EVIDENCE for item in verdict.evidence_refs):
                    raise EvaluationError("V2/V3 passed criterion requires direct, canonical, authoritative, user, or independent evidence")
        independence = _INDEPENDENCE_RANK[self.independence]
        if level >= 2 and independence < _INDEPENDENCE_RANK[Independence.FRESH_CONTEXT]:
            raise EvaluationError("V2 evaluation requires at least a fresh evaluation context")
        if level >= 3 and independence < _INDEPENDENCE_RANK[Independence.INDEPENDENT_MODEL]:
            raise EvaluationError("V3 evaluation requires an independent model/evaluator or authoritative external verification")
        if self.independence == Independence.FRESH_CONTEXT:
            if not self.builder_context_id or not self.evaluator_context_id:
                raise EvaluationError("fresh-context evaluation requires builder and evaluator context ids")
            if self.builder_context_id == self.evaluator_context_id:
                raise EvaluationError("fresh evaluator context must differ from builder context")

    @property
    def overall(self) -> str:
        statuses = [item.status for item in self.verdicts]
        if any(status == "failed" for status in statuses):
            return "failed"
        if any(status in {"unverified", "insufficient_evidence"} for status in statuses):
            return "insufficient_evidence"
        if statuses and all(status in {"passed", "not_applicable"} for status in statuses) and any(status == "passed" for status in statuses):
            return "passed"
        return "mixed"


class EvaluationService:
    def __init__(self, controller: "BrainController"):
        self.controller = controller

    @staticmethod
    def _unique_evidence(verdicts: List[CriterionVerdict]) -> List[EvidenceRef]:
        result: List[EvidenceRef] = []
        seen = set()
        for verdict in verdicts:
            for evidence in verdict.evidence_refs:
                if evidence.ref not in seen:
                    seen.add(evidence.ref)
                    result.append(evidence)
        return result

    def record(self, scope: str, result: EvaluationResult, *, actor: str = "evaluator") -> BrainObject:
        result.validate()
        payload = {
            "target_ref": result.target_ref,
            "verification_level": result.verification_level,
            "independence": result.independence.value,
            "verdicts": [item.to_dict() for item in result.verdicts],
            "overall": result.overall,
            "evaluator_id": result.evaluator_id,
            "builder_context_id": result.builder_context_id,
            "evaluator_context_id": result.evaluator_context_id,
            "notes": result.notes,
        }
        return self.controller.create(
            "evaluation", scope, "RECORDED", payload,
            source=AuthorityTier.VERIFIED_EVIDENCE,
            actor=actor,
            source_refs=[result.target_ref],
            evidence_refs=self._unique_evidence(result.verdicts),
        )

    def apply_to_objective(self, scope: str, objective_id: str, result: EvaluationResult, *, actor: str = "evaluator") -> BrainObject:
        result.validate()
        objective = self.controller.store.load("objective", scope, objective_id)
        if objective.status != "VERIFYING":
            raise EvaluationError(f"objective must be VERIFYING before evaluation is applied, not {objective.status}")
        if result.target_ref != objective_id:
            raise EvaluationError("evaluation target_ref does not match objective")
        floor = objective.payload.get("verification_level", "V0")
        if floor not in _LEVEL_RANK:
            raise ValidationError(f"invalid objective verification_level: {floor}")
        if _LEVEL_RANK[result.verification_level] < _LEVEL_RANK[floor]:
            raise EvaluationError(f"evaluation level {result.verification_level} is below objective floor {floor}")

        criteria = objective.payload.get("criteria", [])
        known_ids = {item["id"] for item in criteria}
        verdict_map = {item.criterion_id: item for item in result.verdicts}
        unknown = sorted(set(verdict_map) - known_ids)
        if unknown:
            raise EvaluationError("evaluation contains unknown criterion ids: " + ", ".join(unknown))

        evaluation = self.record(scope, result, actor=actor)
        expected = objective.revision
        all_evidence = self._unique_evidence(result.verdicts)
        existing_obj_evidence = {item.ref for item in objective.evidence_refs}
        for evidence in all_evidence:
            if evidence.ref not in existing_obj_evidence:
                objective.evidence_refs.append(evidence)
                existing_obj_evidence.add(evidence.ref)

        materialized = []
        for criterion in criteria:
            updated = dict(criterion)
            verdict = verdict_map.get(criterion["id"])
            if verdict is None:
                updated["status"] = "insufficient_evidence"
                updated["evidence_refs"] = []
            else:
                updated["status"] = verdict.status
                updated["evidence_refs"] = [item.ref for item in verdict.evidence_refs]
                if verdict.rationale is not None:
                    updated["evaluation_rationale"] = verdict.rationale
            materialized.append(updated)

        objective.payload["criteria"] = materialized
        evaluation_refs = list(objective.payload.get("evaluation_refs") or [])
        if evaluation.id not in evaluation_refs:
            evaluation_refs.append(evaluation.id)
        objective.payload["evaluation_refs"] = evaluation_refs

        statuses = [item["status"] for item in materialized]
        if any(status == "failed" for status in statuses):
            target = "FAILED"
            objective.payload["progress"] = "complete_unverified"
        elif any(status in {"unverified", "insufficient_evidence"} for status in statuses) or not any(status == "passed" for status in statuses):
            target = "INSUFFICIENT_EVIDENCE"
            objective.payload["progress"] = "complete_unverified"
        elif all(status in {"passed", "not_applicable"} for status in statuses):
            target = "PASSED"
            objective.payload["progress"] = "verified_complete"
        else:
            target = "INSUFFICIENT_EVIDENCE"
            objective.payload["progress"] = "complete_unverified"

        objective.updated_by = actor
        self.controller.store.save(objective, expected_revision=expected)
        return self.controller.transition(
            "objective", scope, objective_id, target,
            source=AuthorityTier.VERIFIED_EVIDENCE, actor=actor,
        )
