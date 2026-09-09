from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from .authority import AuthorityTier, require_user_authority
from .errors import AuthorityError, ValidationError
from .models import BrainObject, EvidenceRef
from .policy import BrainPolicy

if TYPE_CHECKING:
    from .controller import BrainController

_OBSERVATIONAL_CLASSES = {
    "CANONICAL_STATE", "DIRECT_MEASUREMENT", "AUTHORITATIVE_EXTERNAL",
    "INDEPENDENT_EVALUATION", "CORROBORATED_HISTORY", "SINGLE_OBSERVATION",
}


def assert_learning_transition(obj: BrainObject, target: str, source: AuthorityTier) -> None:
    payload = obj.payload
    observations = int(payload.get("independent_observations", 0))
    controlled = int(payload.get("controlled_evaluations", 0))
    contradictions = int(payload.get("contradiction_count", 0))
    user_confirmed = bool(payload.get("user_confirmed", False))
    if target == "PATTERN" and observations < 2 and not user_confirmed:
        raise ValidationError("learning cannot become PATTERN without repeated independent observations or user confirmation")
    if target == "VALIDATED_LEARNING":
        if contradictions:
            raise ValidationError("contradicted learning cannot be validated")
        if controlled < 1 and observations < 3 and not user_confirmed:
            raise ValidationError("validated learning requires controlled evaluation, 3 independent observations, or user confirmation")
    if target == "PROMOTED":
        if not payload.get("strategy_ref"):
            raise ValidationError("promoted learning requires strategy_ref")
        if not payload.get("evaluation_refs"):
            raise ValidationError("promoted learning requires evaluation_refs")
    if source == AuthorityTier.EXTERNAL_DATA:
        raise AuthorityError("external data cannot directly drive learning lifecycle control")


def assert_strategy_activation(obj: BrainObject, source: AuthorityTier, policy: BrainPolicy) -> None:
    tier = obj.payload.get("evolution_tier")
    evaluations = len(set(obj.payload.get("evaluation_refs") or []))
    regression_passed = obj.payload.get("regression_passed") is True
    if tier == "E0":
        raise ValidationError("E0 tactics are ephemeral and cannot be promoted as canonical strategy rules")
    if tier in {"E3", "E4"}:
        raise AuthorityError(
            f"{tier} cannot be activated by runtime Brain state; E3 requires tested code/PR promotion and E4 is privileged authority policy"
        )
    if source > AuthorityTier.VALIDATED_STRATEGY:
        raise AuthorityError("strategy activation requires validated strategy authority or stronger")
    if tier == "E1":
        if evaluations < policy.evolution.e1_min_evaluations:
            raise ValidationError("E1 strategy lacks required evaluations")
        if not regression_passed:
            raise ValidationError("E1 strategy requires regression_passed=true")
        if not policy.evolution.allow_e1_auto_promotion:
            require_user_authority(source, "E1 strategy promotion")
        return
    if tier == "E2":
        if evaluations < policy.evolution.e2_min_evaluations:
            raise ValidationError("E2 strategy lacks required evaluations")
        if not regression_passed:
            raise ValidationError("E2 strategy requires regression_passed=true")
        if policy.evolution.e2_requires_user_approval:
            require_user_authority(source, "E2 strategy promotion")
        return
    raise ValidationError(f"unknown strategy evolution tier: {tier}")


class LearningService:
    def __init__(self, controller: "BrainController"):
        self.controller = controller

    @staticmethod
    def _count_observational(evidence: List[EvidenceRef]) -> int:
        return sum(1 for item in evidence if item.evidence_class in _OBSERVATIONAL_CLASSES)

    def record_observation(
        self,
        scope: str,
        statement: str,
        evidence_refs: List[EvidenceRef],
        *,
        source: AuthorityTier = AuthorityTier.TEMPORARY_HYPOTHESIS,
        applicability: Optional[List[str]] = None,
        actor: str = "brain",
    ) -> BrainObject:
        if not evidence_refs:
            raise ValidationError("learning observation requires evidence")
        if source == AuthorityTier.EXTERNAL_DATA:
            raise AuthorityError("external data must be interpreted before it can create learning state")
        unique = {item.ref: item for item in evidence_refs}
        evidence = list(unique.values())
        contains_user_confirmation = any(item.evidence_class == "USER_CONFIRMATION" for item in evidence)
        if contains_user_confirmation and source > AuthorityTier.EXPLICIT_USER:
            raise AuthorityError("USER_CONFIRMATION evidence requires explicit user authority")
        controlled = sum(1 for item in evidence if item.evidence_class == "INDEPENDENT_EVALUATION")
        user_confirmed = contains_user_confirmation and source <= AuthorityTier.EXPLICIT_USER
        payload = {
            "statement": statement,
            "evidence_strength": "user_confirmed" if user_confirmed else ("controlled" if controlled else "single_observation"),
            "causal_claim": "none",
            "applicability": list(applicability or []),
            "independent_observations": self._count_observational(evidence),
            "controlled_evaluations": controlled,
            "contradiction_count": 0,
            "user_confirmed": user_confirmed,
            "evaluation_refs": [item.ref for item in evidence if item.evidence_class == "INDEPENDENT_EVALUATION"],
            "strategy_ref": None,
        }
        return self.controller.create(
            "learning", scope, "OBSERVATION", payload,
            source=source, actor=actor, evidence_refs=evidence,
        )

    def add_evidence(
        self,
        scope: str,
        learning_id: str,
        evidence_refs: List[EvidenceRef],
        *,
        source: AuthorityTier,
        contradiction: bool = False,
        actor: str = "brain",
    ) -> BrainObject:
        if not evidence_refs:
            raise ValidationError("learning evidence list cannot be empty")
        if any(item.evidence_class == "USER_CONFIRMATION" for item in evidence_refs) and source > AuthorityTier.EXPLICIT_USER:
            raise AuthorityError("USER_CONFIRMATION evidence requires explicit user authority")
        obj = self.controller.store.load("learning", scope, learning_id)
        expected = obj.revision
        existing = {item.ref for item in obj.evidence_refs}
        new_items = [item for item in evidence_refs if item.ref not in existing]
        if not new_items:
            return obj
        obj.evidence_refs.extend(new_items)
        payload = obj.payload
        payload["independent_observations"] = int(payload.get("independent_observations", 0)) + self._count_observational(new_items)
        payload["controlled_evaluations"] = int(payload.get("controlled_evaluations", 0)) + sum(
            1 for item in new_items if item.evidence_class == "INDEPENDENT_EVALUATION"
        )
        if contradiction:
            payload["contradiction_count"] = int(payload.get("contradiction_count", 0)) + len(new_items)
        if any(item.evidence_class == "USER_CONFIRMATION" for item in new_items) and source <= AuthorityTier.EXPLICIT_USER:
            payload["user_confirmed"] = True
            payload["evidence_strength"] = "user_confirmed"
        elif payload["controlled_evaluations"]:
            payload["evidence_strength"] = "controlled"
        elif int(payload.get("independent_observations", 0)) >= 2:
            payload["evidence_strength"] = "corroborated"
        eval_refs = list(payload.get("evaluation_refs") or [])
        for item in new_items:
            if item.evidence_class == "INDEPENDENT_EVALUATION" and item.ref not in eval_refs:
                eval_refs.append(item.ref)
        payload["evaluation_refs"] = eval_refs
        obj.updated_by = actor
        return self.controller.store.save(obj, expected_revision=expected)

    def create_strategy_candidate(
        self,
        scope: str,
        learning_id: str,
        *,
        evolution_tier: str,
        applies_when: List[str],
        instruction: List[str],
        exclusions: Optional[List[str]] = None,
        regression_passed: bool = False,
        actor: str = "brain",
    ) -> BrainObject:
        learning = self.controller.store.load("learning", scope, learning_id)
        if learning.status != "VALIDATED_LEARNING":
            raise ValidationError("strategy candidate requires VALIDATED_LEARNING source")
        payload = {
            "evolution_tier": evolution_tier,
            "applies_when": list(applies_when),
            "instruction": list(instruction),
            "exclusions": list(exclusions or []),
            "helpful_evidence_count": 0,
            "harmful_evidence_count": 0,
            "evaluation_refs": list(learning.payload.get("evaluation_refs") or []),
            "regression_passed": regression_passed,
            "source_learning_ref": learning.id,
            "previous_revision_ref": None,
        }
        strategy = self.controller.create(
            "strategy_rule", scope, "CANDIDATE", payload,
            source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
            source_refs=[learning.id], evidence_refs=list(learning.evidence_refs),
        )
        expected = learning.revision
        learning.payload["strategy_ref"] = strategy.id
        learning.updated_by = actor
        self.controller.store.save(learning, expected_revision=expected)
        try:
            self.controller.transition(
                "learning", scope, learning.id, "STRATEGY_CANDIDATE",
                source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
            )
        except Exception:
            try:
                self.controller.transition(
                    "strategy_rule", scope, strategy.id, "REJECTED",
                    source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
                )
            finally:
                raise
        return strategy

    def record_strategy_outcome(
        self,
        scope: str,
        strategy_id: str,
        *,
        evaluation_ref: str,
        helpful: bool,
        regression_passed: Optional[bool] = None,
        actor: str = "evaluator",
    ) -> BrainObject:
        if not evaluation_ref:
            raise ValidationError("strategy outcome requires evaluation_ref")
        obj = self.controller.store.load("strategy_rule", scope, strategy_id)
        expected = obj.revision
        key = "helpful_evidence_count" if helpful else "harmful_evidence_count"
        obj.payload[key] = int(obj.payload.get(key, 0)) + 1
        refs = list(obj.payload.get("evaluation_refs") or [])
        if evaluation_ref not in refs:
            refs.append(evaluation_ref)
        obj.payload["evaluation_refs"] = refs
        if regression_passed is not None:
            obj.payload["regression_passed"] = bool(regression_passed)
        obj.updated_by = actor
        return self.controller.store.save(obj, expected_revision=expected)
