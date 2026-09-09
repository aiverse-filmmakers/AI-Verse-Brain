from typing import Any, Dict

from .errors import ValidationError
from .models import parse_timestamp

_REQUIRED = {
    "intent": ("subtype", "statement"),
    "practice": ("statement", "health"),
    "gap": ("desired_state_refs", "current_state_refs", "interpretation"),
    "opportunity": ("gap_refs", "hypothesis", "confidence"),
    "initiative": ("serves", "gap_refs", "hypothesis", "outcome", "score_components"),
    "objective": ("outcome", "criteria", "progress"),
    "model_belief": ("domain", "statement", "epistemic_state", "confidence"),
    "evaluation": ("target_ref", "verification_level", "verdicts"),
    "learning": ("statement", "evidence_strength"),
    "strategy_rule": ("evolution_tier", "applies_when", "instruction"),
    "policy": (),
}

_STATUSES = {
    "intent": {"DRAFT", "PROPOSED", "CONFIRMED", "ACTIVE", "PAUSED", "ACHIEVED", "ABANDONED", "SUPERSEDED"},
    "practice": {"DRAFT", "PROPOSED", "CONFIRMED", "ACTIVE", "PAUSED", "RETIRED"},
    "gap": {"ACTIVE", "RESOLVED", "INVALIDATED"},
    "opportunity": {"DETECTED", "DISMISSED", "EXPIRED", "WATCHING", "QUALIFIED", "PROPOSED_INITIATIVE"},
    "initiative": {"DISCOVERED", "PROPOSED", "REJECTED", "DEFERRED", "ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "PAUSED", "REVIEW", "COMPLETED", "ABANDONED", "SUPERSEDED"},
    "objective": {"QUEUED", "READY", "RUNNING", "WAITING", "BLOCKED", "STALLED", "VERIFYING", "PASSED", "FAILED", "INSUFFICIENT_EVIDENCE", "CANCELLED", "SUPERSEDED"},
    "model_belief": {"ACTIVE", "RETIRED", "CONTRADICTED"},
    "evaluation": {"RECORDED", "SUPERSEDED"},
    "learning": {"OBSERVATION", "HYPOTHESIS", "PATTERN", "REFLECTION", "VALIDATED_LEARNING", "STRATEGY_CANDIDATE", "PROMOTED", "REJECTED"},
    "strategy_rule": {"CANDIDATE", "ACTIVE", "RETIRED", "ROLLED_BACK", "REJECTED"},
    "policy": {"ACTIVE", "SUPERSEDED"},
}

_ENUMS = {
    ("intent", "subtype"): {"desired_state", "goal", "boundary", "constraint", "success_definition"},
    ("practice", "health"): {"UNKNOWN", "HEALTHY", "AT_RISK", "DEGRADED", "BREACHED"},
    ("model_belief", "domain"): {"user_model", "agent_model", "world_model"},
    ("model_belief", "epistemic_state"): {"known", "inferred", "assumed", "unknown", "contradicted", "stale"},
    ("objective", "progress"): {"progressing", "waiting", "blocked", "stalled", "wrong_strategy", "invalidated", "complete_unverified", "verified_complete"},
    ("strategy_rule", "evolution_tier"): {"E0", "E1", "E2", "E3", "E4"},
    ("evaluation", "verification_level"): {"V0", "V1", "V2", "V3"},
    ("evaluation", "independence"): {"same_context", "fresh_context", "independent_model", "external_authoritative"},
    ("learning", "evidence_strength"): {"single_observation", "corroborated", "controlled", "user_confirmed"},
    ("learning", "causal_claim"): {"none", "plausible", "controlled_support"},
}

_LIST_FIELDS = {
    ("gap", "desired_state_refs"), ("gap", "current_state_refs"),
    ("opportunity", "gap_refs"), ("initiative", "serves"), ("initiative", "gap_refs"),
    ("objective", "criteria"), ("evaluation", "verdicts"),
    ("strategy_rule", "applies_when"), ("strategy_rule", "instruction"),
}


def _require_nonempty_list(kind: str, payload: Dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{kind}.{field} must be a non-empty list")


def _require_nonnegative_int(kind: str, payload: Dict[str, Any], field: str) -> None:
    if field not in payload:
        return
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValidationError(f"{kind}.{field} must be an integer >= 0")


def validate_payload(kind: str, payload: Dict[str, Any]) -> None:
    if kind not in _REQUIRED:
        raise ValidationError(f"unknown payload kind: {kind}")
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")
    missing = [field for field in _REQUIRED[kind] if field not in payload]
    if missing:
        raise ValidationError(f"{kind} payload missing required fields: {', '.join(missing)}")
    for (enum_kind, field), allowed in _ENUMS.items():
        if kind == enum_kind and field in payload and payload[field] is not None and payload[field] not in allowed:
            raise ValidationError(f"invalid {kind}.{field}: {payload[field]!r}")
    for list_kind, field in _LIST_FIELDS:
        if kind == list_kind:
            _require_nonempty_list(kind, payload, field)
    if "confidence" in payload:
        confidence = payload["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            raise ValidationError(f"{kind}.confidence must be normalized to [0,1]")

    if kind == "opportunity" and payload.get("expires_at"):
        parse_timestamp(payload["expires_at"], field_name="opportunity.expires_at")

    if kind == "initiative":
        if not isinstance(payload.get("score_components"), dict):
            raise ValidationError("initiative.score_components must be an object")
        if "evaluation_refs" in payload and not isinstance(payload["evaluation_refs"], list):
            raise ValidationError("initiative.evaluation_refs must be a list")

    if kind == "objective":
        ids = []
        for criterion in payload["criteria"]:
            if not isinstance(criterion, dict) or not {"id", "statement", "status"}.issubset(criterion):
                raise ValidationError("objective criteria require id, statement, and status")
            if not isinstance(criterion["id"], str) or not criterion["id"].strip():
                raise ValidationError("objective criterion id must be non-empty")
            ids.append(criterion["id"])
            if criterion["status"] not in {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}:
                raise ValidationError(f"invalid objective criterion status: {criterion['status']}")
            if criterion["status"] == "passed" and not criterion.get("evidence_refs"):
                raise ValidationError("passed objective criterion requires evidence_refs")
        if len(ids) != len(set(ids)):
            raise ValidationError("objective criterion ids must be unique")
        if "stall_threshold" in payload:
            value = payload["stall_threshold"]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValidationError("objective.stall_threshold must be an integer >= 1")
        budget = payload.get("budget")
        if budget is not None:
            if not isinstance(budget, dict):
                raise ValidationError("objective.budget must be an object")
            if "max_attempts" in budget:
                value = budget["max_attempts"]
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    raise ValidationError("objective.budget.max_attempts must be an integer >= 1")
        if "verification_level" in payload and payload["verification_level"] not in {"V0", "V1", "V2", "V3"}:
            raise ValidationError("invalid objective.verification_level")

    if kind == "model_belief":
        for field in ("observed_at", "expires_at", "last_reviewed"):
            if payload.get(field):
                parse_timestamp(payload[field], field_name=f"model_belief.{field}")
        if "max_age_seconds" in payload and payload["max_age_seconds"] is not None:
            _require_nonnegative_int(kind, payload, "max_age_seconds")
        if "contradiction_refs" in payload and not isinstance(payload["contradiction_refs"], list):
            raise ValidationError("model_belief.contradiction_refs must be a list")

    if kind == "evaluation":
        ids = []
        for verdict in payload["verdicts"]:
            if not isinstance(verdict, dict) or not {"criterion_id", "status"}.issubset(verdict):
                raise ValidationError("evaluation verdicts require criterion_id and status")
            ids.append(verdict["criterion_id"])
            if verdict["status"] not in {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}:
                raise ValidationError(f"invalid evaluation verdict status: {verdict['status']}")
            if verdict["status"] == "passed" and not verdict.get("evidence_refs"):
                raise ValidationError("passed evaluation verdict requires evidence_refs")
        if len(ids) != len(set(ids)):
            raise ValidationError("evaluation verdict criterion ids must be unique")

    if kind == "learning":
        for field in ("independent_observations", "controlled_evaluations", "contradiction_count"):
            _require_nonnegative_int(kind, payload, field)
        if "evaluation_refs" in payload and not isinstance(payload["evaluation_refs"], list):
            raise ValidationError("learning.evaluation_refs must be a list")

    if kind == "strategy_rule":
        for field in ("helpful_evidence_count", "harmful_evidence_count"):
            _require_nonnegative_int(kind, payload, field)
        if "evaluation_refs" in payload and not isinstance(payload["evaluation_refs"], list):
            raise ValidationError("strategy_rule.evaluation_refs must be a list")
        if "regression_passed" in payload and not isinstance(payload["regression_passed"], bool):
            raise ValidationError("strategy_rule.regression_passed must be boolean")


def validate_object(kind: str, status: str, payload: Dict[str, Any]) -> None:
    if kind not in _STATUSES:
        raise ValidationError(f"unknown object kind: {kind}")
    if status not in _STATUSES[kind]:
        raise ValidationError(f"invalid {kind} status: {status}")
    validate_payload(kind, payload)
