from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, TYPE_CHECKING

from .authority import AuthorityTier, require_user_authority
from .errors import AuthorityError, ValidationError
from .models import BrainObject, EvidenceRef, Scope
from .policy import BrainPolicy

if TYPE_CHECKING:
    from .controller import BrainController

_OBSERVATIONAL_CLASSES = {
    "CANONICAL_STATE", "DIRECT_MEASUREMENT", "AUTHORITATIVE_EXTERNAL",
    "INDEPENDENT_EVALUATION", "CORROBORATED_HISTORY", "SINGLE_OBSERVATION",
}

_LEARNING_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
_SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SKILLS_ROUTE_KINDS = {"create", "repair"}
_SKILLS_ROUTE_OWNERS = {"agent_learned", "workspace_local"}
_SKILLS_ROUTE_FIELDS = {
    "candidate_id", "scope", "suggested_owner", "kind", "summary", "skill_id",
    "target_skill_id", "evidence_refs", "success_signal", "failure_signal", "risk",
    "confidence", "created_at", "requested_capabilities", "requested_dependencies",
    "requires_connection", "requires_credential", "source_ownership",
}
_FORBIDDEN_LEARNING_FIELDS = {
    "raw_transcript", "credentials", "secrets", "private_key", "raw_tool_output",
    "permission_grant", "authorization", "approval",
}


def _bounded_string_list(value: Any, label: str, *, required: bool = False) -> List[str]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    if required and not value:
        raise ValidationError(f"{label} must not be empty")
    if len(value) > 32:
        raise ValidationError(f"{label} exceeds 32 entries")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 500:
            raise ValidationError(f"{label} entries must be non-empty strings <= 500 characters")
        text = item.strip()
        if text not in result:
            result.append(text)
    return result


def admit_skills_learning_candidate(
    candidate: Mapping[str, Any],
    *,
    bound_scope: str,
    substantial_task: bool,
) -> Dict[str, Any]:
    """Brain-owned deterministic gate for cross-owner reusable-procedure candidates.

    The model/runtime may suggest a candidate. Brain decides whether that bounded
    suggestion is eligible to be routed to Skills. Skills still owns proposal
    evaluation, security/admission, immutable promotion and rollback.
    """

    Scope(bound_scope)
    if not isinstance(candidate, Mapping):
        raise ValidationError("learning candidate must be an object")
    if not substantial_task:
        return {
            "state": "ignored",
            "reason": "task evidence is not substantial enough for a learning review",
            "suggested_owner": "none",
        }

    data = dict(candidate)
    forbidden = sorted(_FORBIDDEN_LEARNING_FIELDS.intersection(data))
    if forbidden:
        raise ValidationError("learning candidate contains forbidden raw/authority fields: " + ", ".join(forbidden))
    extras = sorted(set(data) - _SKILLS_ROUTE_FIELDS)
    if extras:
        raise ValidationError("learning candidate contains unsupported fields: " + ", ".join(extras))

    candidate_id = data.get("candidate_id")
    if not isinstance(candidate_id, str) or not _LEARNING_CANDIDATE_ID.fullmatch(candidate_id):
        raise ValidationError("candidate_id must be a bounded stable identifier")

    scope = data.get("scope")
    if scope != bound_scope:
        raise ValidationError("learning candidate scope must equal the trusted bound scope")

    if data.get("suggested_owner") != "skills":
        return {
            "state": "ignored",
            "reason": f"candidate belongs to {data.get('suggested_owner') or 'another owner'}, not Skills",
            "suggested_owner": data.get("suggested_owner"),
        }

    kind = data.get("kind")
    if kind not in _SKILLS_ROUTE_KINDS:
        return {
            "state": "ignored",
            "reason": f"{kind!r} is not a foreground reusable-procedure route",
            "suggested_owner": "skills",
        }

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 2000:
        raise ValidationError("learning candidate summary must be a non-empty string <= 2000 characters")

    risk = data.get("risk")
    if risk not in {"low", "medium", "high"}:
        raise ValidationError("learning candidate risk must be low, medium, or high")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValidationError("learning candidate confidence must be numeric")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValidationError("learning candidate confidence must be within 0..1")
    if confidence < 0.6:
        return {
            "state": "ignored",
            "reason": "candidate confidence is below Brain's routing threshold",
            "suggested_owner": "skills",
        }

    evidence_refs = _bounded_string_list(data.get("evidence_refs"), "evidence_refs", required=True)
    success_signal = _bounded_string_list(data.get("success_signal"), "success_signal")
    failure_signal = _bounded_string_list(data.get("failure_signal"), "failure_signal")
    requested_capabilities = _bounded_string_list(data.get("requested_capabilities"), "requested_capabilities")
    requested_dependencies = _bounded_string_list(data.get("requested_dependencies"), "requested_dependencies")

    source_ownership = data.get("source_ownership", "agent_learned")
    if source_ownership not in _SKILLS_ROUTE_OWNERS:
        raise ValidationError("runtime-routed Skills candidates must be agent_learned or workspace_local")

    skill_id = data.get("skill_id")
    target_skill_id = data.get("target_skill_id")
    if kind == "create":
        if not isinstance(skill_id, str) or not _SKILL_ID.fullmatch(skill_id):
            raise ValidationError("create candidate requires a safe skill_id")
        if target_skill_id not in {None, ""}:
            raise ValidationError("create candidate must not name a target_skill_id")
    else:
        if not isinstance(target_skill_id, str) or not _SKILL_ID.fullmatch(target_skill_id):
            raise ValidationError("repair candidate requires a safe target_skill_id")
        if skill_id not in {None, "", target_skill_id}:
            raise ValidationError("repair candidate skill_id may only match target_skill_id")

    for flag in ("requires_connection", "requires_credential"):
        if flag in data and not isinstance(data[flag], bool):
            raise ValidationError(f"{flag} must be boolean")

    created_at = data.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip() or len(created_at) > 100:
        raise ValidationError("learning candidate created_at must be a bounded timestamp string")

    skills_scope: Dict[str, str] = {"aiverse_scope": bound_scope}
    if source_ownership == "workspace_local":
        if not bound_scope.startswith("workspace:"):
            raise ValidationError("workspace_local candidate requires a workspace-bound task")
        skills_scope = {"workspace_id": bound_scope.split(":", 1)[1]}

    envelope: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "scope": skills_scope,
        "suggested_owner": "skills",
        "kind": kind,
        "summary": summary.strip(),
        "evidence_refs": evidence_refs,
        "success_signal": success_signal,
        "failure_signal": failure_signal,
        "risk": risk,
        "confidence": confidence,
        "requested_capabilities": requested_capabilities,
        "requested_dependencies": requested_dependencies,
        "requires_connection": bool(data.get("requires_connection", False)),
        "requires_credential": bool(data.get("requires_credential", False)),
        "source_ownership": source_ownership,
    }
    if kind == "create":
        envelope["skill_id"] = skill_id
    else:
        envelope["target_skill_id"] = target_skill_id

    return {
        "state": "admitted",
        "reason": "substantial reusable-procedure candidate passed Brain routing admission",
        "suggested_owner": "skills",
        "envelope": envelope,
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
