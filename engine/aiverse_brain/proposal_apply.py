from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .authority import AuthorityTier
from .cognition import CognitionProposal, CognitionRequest, validate_proposal
from .direction import GapProposal, InitiativeProposal, OpportunityProposal
from .errors import CognitionContractError, ValidationError
from .models import BrainObject, EvidenceRef, parse_timestamp, utc_now
from .ranking import Eligibility, NotificationClass, ScoreComponents
from .verification import VerificationFactors, VerificationLevel, select_level


_SCORE_FIELDS = (
    "goal_alignment", "expected_impact", "urgency", "confidence",
    "strategic_leverage", "readiness_4c", "reversibility",
    "effort_cost", "attention_cost", "risk", "opportunity_cost",
)
_SCORE_FIELD_SET = set(_SCORE_FIELDS)
_FACTOR_FIELDS = set(VerificationFactors.__dataclass_fields__)
_ACTIVE_INTENT = {"CONFIRMED", "ACTIVE"}
_DESIRED_INTENT_SUBTYPES = {"desired_state", "goal", "success_definition"}
_ACTIVE_INITIATIVE = {"ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "REVIEW"}


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[\w'-]+", text.casefold(), flags=re.UNICODE))


def _require_text(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_text(payload: Dict[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string when provided")
    return value.strip()


def _require_string_list(payload: Dict[str, Any], key: str) -> List[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{key} must be a non-empty list")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(f"{key} entries must be non-empty strings")
        result.append(item.strip())
    return result


def _optional_string_list(payload: Dict[str, Any], key: str) -> List[str]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{key} must be a list")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(f"{key} entries must be non-empty strings")
        result.append(item.strip())
    return result


@dataclass(frozen=True)
class AppliedProposal:
    proposal_kind: str
    object_id: str
    object_ref: str
    status: str
    notification: NotificationClass = NotificationClass.STORE
    attention_fingerprint: Optional[str] = None
    duplicate: bool = False


class ProposalApplier:
    """Maps advisory model proposals into deterministic Brain domain operations."""

    MIN_OPPORTUNITY_CONFIDENCE = 0.55

    def __init__(self, controller: Any):
        self.controller = controller

    def _existing_exact(self, kind: str, scope: str, *, predicate: Any) -> Optional[BrainObject]:
        for obj in self.controller.store.list(kind, scope):
            if predicate(obj):
                return obj
        return None

    def _load_object(self, kind: str, scope: str, object_id: str, *, label: str) -> BrainObject:
        try:
            return self.controller.store.load(kind, scope, object_id)
        except (FileNotFoundError, KeyError) as exc:
            raise ValidationError(f"{label} does not resolve to canonical {kind} state: {object_id}") from exc

    def _resolve_desired_ref(self, scope: str, ref: str) -> Tuple[str, BrainObject]:
        if not isinstance(ref, str) or not ref.strip():
            raise ValidationError("desired state ref must be a non-empty string")
        text = ref.strip()
        if text.startswith("brain:"):
            text = text[6:]
        if ":" not in text:
            raise ValidationError("desired state ref must identify intent:<id>")
        kind, object_id = text.split(":", 1)
        if kind != "intent" or not object_id:
            raise ValidationError("desired state ref must identify canonical intent:<id>")
        obj = self._load_object("intent", scope, object_id, label="desired state ref")
        if obj.status not in _ACTIVE_INTENT:
            raise ValidationError(f"desired intent is not confirmed/active: {object_id} ({obj.status})")
        subtype = obj.payload.get("subtype")
        if subtype not in _DESIRED_INTENT_SUBTYPES:
            raise ValidationError(
                f"intent {object_id} is {subtype!r}, not a desired state/goal/success definition"
            )
        return f"brain:intent:{object_id}", obj

    def _validate_current_ref(self, request: CognitionRequest, ref: str) -> str:
        if not isinstance(ref, str) or not ref.strip():
            raise ValidationError("current state ref must be a non-empty string")
        text = ref.strip()
        if text == "host:current":
            return text
        brain_text = text[6:] if text.startswith("brain:") else text
        if brain_text.startswith("model_belief:"):
            object_id = brain_text.split(":", 1)[1]
            belief = self._load_object("model_belief", request.scope.value, object_id, label="current state ref")
            if belief.status != "ACTIVE":
                raise ValidationError(f"current-state belief is not active: {object_id} ({belief.status})")
            if belief.payload.get("epistemic_state") in {"unknown", "stale", "contradicted"}:
                raise ValidationError(
                    f"current-state belief is not usable: {object_id} ({belief.payload.get('epistemic_state')})"
                )
            return f"brain:model_belief:{object_id}"
        if text.startswith("brain:"):
            raise ValidationError("current state ref may not reinterpret another Brain control object as observed state")
        allowed = set(request.context_refs) | set(request.evidence_refs)
        if text not in allowed:
            raise ValidationError(f"current state ref was not present in bounded cognition context: {text}")
        return text

    def _fresh_gap_evidence(self, gaps: Sequence[BrainObject]) -> bool:
        now = datetime.now(timezone.utc)
        for gap in gaps:
            for evidence in gap.evidence_refs:
                if evidence.expires_at and parse_timestamp(
                    evidence.expires_at, field_name="evidence.expires_at"
                ) <= now:
                    return False
        return True

    def _score_components(self, payload: Dict[str, Any], confidence: float) -> ScoreComponents:
        raw = payload.get("score_components")
        if not isinstance(raw, dict):
            raise ValidationError("opportunity.score_components must be an object")
        extras = sorted(set(raw) - _SCORE_FIELD_SET)
        missing = sorted((_SCORE_FIELD_SET - {"confidence"}) - set(raw))
        if extras:
            raise ValidationError("unknown score components: " + ", ".join(extras))
        if missing:
            raise ValidationError("missing score components: " + ", ".join(missing))
        values: Dict[str, float] = {}
        for name in _SCORE_FIELDS:
            raw_value = raw.get(name, confidence if name == "confidence" else 0.0)
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise ValidationError(f"score component {name} must be numeric")
            values[name] = float(raw_value)
        values["confidence"] = float(confidence)
        components = ScoreComponents(**values)
        components.validate()
        return components

    def _verification_level(self, payload: Dict[str, Any]) -> str:
        raw = payload.get("verification_factors", {})
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValidationError("verification_factors must be an object")
        extras = sorted(set(raw) - _FACTOR_FIELDS)
        if extras:
            raise ValidationError("unknown verification factors: " + ", ".join(extras))
        values: Dict[str, float] = {}
        for name in _FACTOR_FIELDS:
            raw_value = raw.get(name, 0.0)
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise ValidationError(f"verification factor {name} must be numeric")
            values[name] = float(raw_value)
        factors = VerificationFactors(**values)
        level = select_level(factors, policy_floor=VerificationLevel.V1_NORMAL)
        return f"V{int(level)}"

    def _resolve_serves_ref(self, scope: str, ref: str) -> Tuple[str, BrainObject]:
        if not isinstance(ref, str) or not ref.strip():
            raise ValidationError("objective serves_ref is required")
        text = ref.strip()
        if text.startswith("brain:"):
            text = text[6:]
        if ":" not in text:
            raise ValidationError("serves_ref must identify intent:<id> or initiative:<id>")
        kind, object_id = text.split(":", 1)
        if kind not in {"intent", "initiative"} or not object_id:
            raise ValidationError("serves_ref must identify intent:<id> or initiative:<id>")
        obj = self._load_object(kind, scope, object_id, label="objective serves_ref")
        if kind == "intent":
            if obj.status not in _ACTIVE_INTENT:
                raise ValidationError(f"objective cannot serve inactive intent {object_id} ({obj.status})")
            if obj.payload.get("subtype") not in _DESIRED_INTENT_SUBTYPES:
                raise ValidationError("objective may only serve a goal, desired state, or success definition")
        if kind == "initiative" and obj.status not in _ACTIVE_INITIATIVE:
            raise ValidationError(f"objective cannot serve unaccepted initiative {object_id} ({obj.status})")
        return kind, obj

    def _apply_gap(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        payload = proposal.payload
        desired_raw = _require_string_list(payload, "desired_state_refs")
        current_raw = _require_string_list(payload, "current_state_refs")
        desired = [self._resolve_desired_ref(request.scope.value, ref)[0] for ref in desired_raw]
        current = [self._validate_current_ref(request, ref) for ref in current_raw]
        interpretation = _require_text(payload, "interpretation")
        assumptions = _optional_string_list(payload, "assumptions")
        unknowns = _optional_string_list(payload, "unknowns")
        norm = _normalized(interpretation)
        existing = self._existing_exact(
            "gap", request.scope.value,
            predicate=lambda obj: (
                obj.status == "ACTIVE"
                and sorted(obj.payload.get("desired_state_refs", [])) == sorted(desired)
                and sorted(obj.payload.get("current_state_refs", [])) == sorted(current)
                and _normalized(str(obj.payload.get("interpretation", ""))) == norm
            ),
        )
        if existing:
            return AppliedProposal("gap", existing.id, f"brain:gap:{existing.id}", existing.status, duplicate=True)
        obj = self.controller.direction.create_gap(
            request.scope.value,
            GapProposal(desired, current, interpretation, assumptions, unknowns),
            source_refs=list(request.context_refs),
            actor="reasoner:" + proposal.source_model,
        )
        return AppliedProposal("gap", obj.id, f"brain:gap:{obj.id}", obj.status)

    def _apply_opportunity(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        payload = proposal.payload
        gap_refs = _require_string_list(payload, "gap_refs")
        hypothesis = _require_text(payload, "hypothesis")
        gaps = [self._load_object("gap", request.scope.value, gap_id, label="opportunity gap ref") for gap_id in gap_refs]
        desired_state_linked = True
        for gap in gaps:
            if gap.status != "ACTIVE":
                desired_state_linked = False
                continue
            desired_refs = gap.payload.get("desired_state_refs", [])
            if not desired_refs:
                desired_state_linked = False
                continue
            for ref in desired_refs:
                try:
                    self._resolve_desired_ref(request.scope.value, ref)
                except ValidationError:
                    desired_state_linked = False
                    break
        components = self._score_components(payload, proposal.confidence)
        eligibility = Eligibility(
            desired_state_linked=desired_state_linked,
            scope_valid=True,
            permission_compatible=True,
            non_duplicate=True,
            evidence_fresh_enough=self._fresh_gap_evidence(gaps),
            minimum_confidence_met=proposal.confidence >= self.MIN_OPPORTUNITY_CONFIDENCE,
            cooldown_clear=True,
            hard_boundary_clear=True,
        )
        obj, ranked = self.controller.direction.propose_opportunity(
            request.scope.value,
            OpportunityProposal(
                gap_refs=gap_refs,
                hypothesis=hypothesis,
                confidence=float(proposal.confidence),
                mechanism=_optional_text(payload, "mechanism"),
                expires_at=_optional_text(payload, "expires_at"),
                dedupe_key=_optional_text(payload, "dedupe_key"),
            ),
            components,
            eligibility=eligibility,
            source_refs=list(request.context_refs),
            actor="reasoner:" + proposal.source_model,
        )
        if ranked.eligible:
            obj = self.controller.direction.qualify_opportunity(
                request.scope.value, obj.id, actor="brain:eligibility-gate"
            )
        return AppliedProposal(
            "opportunity", obj.id, f"brain:opportunity:{obj.id}", obj.status,
            notification=ranked.notification,
            attention_fingerprint=obj.payload.get("cooldown_fingerprint"),
        )

    def _apply_initiative(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        payload = proposal.payload
        opportunity_id = _require_text(payload, "source_opportunity_ref")
        if opportunity_id.startswith("brain:opportunity:"):
            opportunity_id = opportunity_id.split(":", 2)[2]
        elif opportunity_id.startswith("opportunity:"):
            opportunity_id = opportunity_id.split(":", 1)[1]
        source = self._load_object("opportunity", request.scope.value, opportunity_id, label="source opportunity")
        raw_components = source.payload.get("score_components")
        if not isinstance(raw_components, dict):
            raise ValidationError("qualified source opportunity lacks score components")
        component_values: Dict[str, float] = {}
        for name in _SCORE_FIELDS:
            raw_value = raw_components.get(name)
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise ValidationError(f"source opportunity score component {name} is invalid")
            component_values[name] = float(raw_value)
        components = ScoreComponents(**component_values)
        components.validate()
        serves_raw = _require_string_list(payload, "serves")
        serves = [self._resolve_desired_ref(request.scope.value, ref)[0] for ref in serves_raw]
        obj = self.controller.direction.propose_initiative(
            request.scope.value,
            opportunity_id,
            InitiativeProposal(
                serves=serves,
                gap_refs=_require_string_list(payload, "gap_refs"),
                hypothesis=_require_text(payload, "hypothesis"),
                outcome=_require_text(payload, "outcome"),
                score_components=components,
                next_action=_optional_text(payload, "next_action"),
                review_after=_optional_text(payload, "review_after"),
                invalidation_conditions=_optional_string_list(payload, "invalidation_conditions"),
            ),
            actor="reasoner:" + proposal.source_model,
        )
        rank_result = obj.payload.get("rank_result", {})
        notification_text = rank_result.get("notification", NotificationClass.STORE.value)
        try:
            notification = NotificationClass(notification_text)
        except ValueError:
            notification = NotificationClass.STORE
        return AppliedProposal(
            "initiative", obj.id, f"brain:initiative:{obj.id}", obj.status,
            notification=notification,
            attention_fingerprint=obj.payload.get("source_fingerprint"),
        )

    def _apply_objective(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        payload = proposal.payload
        outcome = _require_text(payload, "outcome")
        serves_ref = _require_text(payload, "serves_ref")
        serves_kind, parent = self._resolve_serves_ref(request.scope.value, serves_ref)
        canonical_serves_ref = f"{serves_kind}:{parent.id}"
        raw_criteria = payload.get("criteria")
        if not isinstance(raw_criteria, list) or not raw_criteria:
            raise ValidationError("objective.criteria must be a non-empty list")
        criteria: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_criteria):
            if not isinstance(item, dict):
                raise ValidationError(f"objective criterion {index} must be an object")
            forbidden = sorted(set(item) & {"status", "evidence_refs", "evaluation_rationale"})
            if forbidden:
                raise CognitionContractError(
                    "model-created objective criteria cannot pre-set verification state: " + ", ".join(forbidden)
                )
            extras = sorted(set(item) - {"id", "statement", "required_evidence"})
            if extras:
                raise ValidationError("unknown objective criterion fields: " + ", ".join(extras))
            criteria.append({
                "id": _require_text(item, "id"),
                "statement": _require_text(item, "statement"),
                "required_evidence": str(item.get("required_evidence", "")),
                "status": "unverified",
                "evidence_refs": [],
            })
        existing = self._existing_exact(
            "objective", request.scope.value,
            predicate=lambda obj: (
                obj.status not in {"PASSED", "CANCELLED", "SUPERSEDED"}
                and _normalized(str(obj.payload.get("outcome", ""))) == _normalized(outcome)
                and obj.payload.get("serves_ref") == canonical_serves_ref
            ),
        )
        if existing:
            return AppliedProposal("objective", existing.id, f"brain:objective:{existing.id}", existing.status, duplicate=True)
        proposed_budget = payload.get("budget", {})
        if proposed_budget is None:
            proposed_budget = {}
        if not isinstance(proposed_budget, dict):
            raise ValidationError("objective.budget must be an object")
        maximum = self.controller.policy.resources.max_objective_attempts
        raw_max_attempts = proposed_budget.get("max_attempts", maximum)
        if not isinstance(raw_max_attempts, int) or isinstance(raw_max_attempts, bool) or raw_max_attempts < 1:
            raise ValidationError("objective budget max_attempts must be an integer >= 1")
        max_attempts = min(raw_max_attempts, maximum)
        default_stall = self.controller.policy.resources.max_non_progressing_attempts_before_stall
        raw_stall_threshold = payload.get("stall_threshold", default_stall)
        if not isinstance(raw_stall_threshold, int) or isinstance(raw_stall_threshold, bool) or raw_stall_threshold < 1:
            raise ValidationError("objective stall_threshold must be an integer >= 1")
        stall_threshold = min(raw_stall_threshold, default_stall)
        obj = self.controller.create(
            "objective", request.scope.value, "QUEUED",
            {
                "outcome": outcome,
                "serves_ref": canonical_serves_ref,
                "serves_object_id": parent.id,
                "criteria": criteria,
                "progress": "waiting",
                "verification_level": self._verification_level(payload),
                "progress_ledger": {},
                "evaluation_refs": [],
                "budget": {"max_attempts": max_attempts},
                "stall_threshold": stall_threshold,
                "constraints": _optional_string_list(payload, "constraints"),
                "boundaries": _optional_string_list(payload, "boundaries"),
                "stop_conditions": _optional_string_list(payload, "stop_conditions"),
                "builder_context_id": request.request_id,
            },
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="reasoner:" + proposal.source_model,
            source_refs=[parent.id] + list(request.context_refs),
        )
        return AppliedProposal("objective", obj.id, f"brain:objective:{obj.id}", obj.status)

    def _apply_belief(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        payload = proposal.payload
        domain = _require_text(payload, "domain")
        if domain not in {"user_model", "agent_model", "world_model"}:
            raise ValidationError("model_belief.domain must be user_model, agent_model, or world_model")
        statement = _require_text(payload, "statement")
        existing = self._existing_exact(
            "model_belief", request.scope.value,
            predicate=lambda obj: (
                obj.status == "ACTIVE"
                and obj.payload.get("epistemic_state") not in {"unknown", "stale", "contradicted"}
                and obj.payload.get("domain") == domain
                and _normalized(str(obj.payload.get("statement", ""))) == _normalized(statement)
            ),
        )
        if existing:
            return AppliedProposal(
                "model_belief", existing.id, f"brain:model_belief:{existing.id}",
                existing.status, duplicate=True,
            )
        domain_max = {"world_model": 86400, "agent_model": 604800, "user_model": 2592000}[domain]
        proposed_max = payload.get("max_age_seconds", domain_max)
        if not isinstance(proposed_max, int) or isinstance(proposed_max, bool) or proposed_max < 60:
            raise ValidationError("model_belief.max_age_seconds must be an integer >= 60")
        now = utc_now()
        obj = self.controller.create(
            "model_belief", request.scope.value, "ACTIVE",
            {
                "domain": domain,
                "statement": statement,
                "epistemic_state": "inferred",
                "confidence": float(proposal.confidence),
                "observed_at": now,
                "max_age_seconds": min(proposed_max, domain_max),
                "contradiction_refs": [],
                "last_reviewed": now,
            },
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            actor="reasoner:" + proposal.source_model,
            source_refs=list(request.context_refs),
        )
        return AppliedProposal("model_belief", obj.id, f"brain:model_belief:{obj.id}", obj.status)

    def _apply_learning(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        payload = proposal.payload
        statement = _require_text(payload, "statement")
        basis = _require_string_list(payload, "basis_refs")
        allowed_basis = set(request.context_refs) | set(request.evidence_refs)
        unknown = sorted(set(basis) - allowed_basis)
        if unknown:
            raise CognitionContractError(
                "learning basis_refs must come from the bounded cognition request: " + ", ".join(unknown)
            )
        existing = self._existing_exact(
            "learning", request.scope.value,
            predicate=lambda obj: (
                obj.status not in {"REJECTED", "PROMOTED"}
                and _normalized(str(obj.payload.get("statement", ""))) == _normalized(statement)
                and sorted(obj.source_refs) == sorted(basis)
            ),
        )
        if existing:
            return AppliedProposal("learning", existing.id, f"brain:learning:{existing.id}", existing.status, duplicate=True)
        evidence = [
            EvidenceRef(
                ref=ref,
                evidence_class="MODEL_INFERENCE",
                claim=statement,
                observed_at=utc_now(),
                scope=request.scope.value,
            )
            for ref in basis
        ]
        obj = self.controller.learning.record_observation(
            request.scope.value,
            statement,
            evidence,
            source=AuthorityTier.TEMPORARY_HYPOTHESIS,
            applicability=_optional_string_list(payload, "applicability"),
            actor="reasoner:" + proposal.source_model,
        )
        expected = obj.revision
        obj.source_refs = list(basis)
        obj.updated_by = "brain:proposal-applier"
        obj = self.controller.store.save(obj, expected_revision=expected)
        return AppliedProposal("learning", obj.id, f"brain:learning:{obj.id}", obj.status)

    def apply(self, request: CognitionRequest, proposal: CognitionProposal) -> AppliedProposal:
        validate_proposal(request, proposal)
        handlers = {
            "gap": self._apply_gap,
            "opportunity": self._apply_opportunity,
            "initiative": self._apply_initiative,
            "objective": self._apply_objective,
            "model_belief": self._apply_belief,
            "learning": self._apply_learning,
        }
        handler = handlers.get(proposal.proposal_kind)
        if handler is None:
            raise CognitionContractError(f"no deterministic applier for {proposal.proposal_kind}")
        return handler(request, proposal)
