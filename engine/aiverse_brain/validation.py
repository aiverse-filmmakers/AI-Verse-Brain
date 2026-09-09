from typing import Any, Dict

from .errors import ValidationError

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


def validate_payload(kind: str, payload: Dict[str, Any]) -> None:
    if kind not in _REQUIRED:
        raise ValidationError(f"unknown payload kind: {kind}")
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")
    missing = [field for field in _REQUIRED[kind] if field not in payload]
    if missing:
        raise ValidationError(f"{kind} payload missing required fields: {', '.join(missing)}")
    for (enum_kind, field), allowed in _ENUMS.items():
        if kind == enum_kind and field in payload and payload[field] not in allowed:
            raise ValidationError(f"invalid {kind}.{field}: {payload[field]!r}")
    for list_kind, field in _LIST_FIELDS:
        if kind == list_kind:
            _require_nonempty_list(kind, payload, field)
    if "confidence" in payload:
        confidence = payload["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            raise ValidationError(f"{kind}.confidence must be normalized to [0,1]")
    if kind == "objective":
        for criterion in payload["criteria"]:
            if not isinstance(criterion, dict) or not {"id", "statement", "status"}.issubset(criterion):
                raise ValidationError("objective criteria require id, statement, and status")
            if criterion["status"] not in {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}:
                raise ValidationError(f"invalid objective criterion status: {criterion['status']}")
            if criterion["status"] == "passed" and not criterion.get("evidence_refs"):
                raise ValidationError("passed objective criterion requires evidence_refs")


def validate_object(kind: str, status: str, payload: Dict[str, Any]) -> None:
    if kind not in _STATUSES:
        raise ValidationError(f"unknown object kind: {kind}")
    if status not in _STATUSES[kind]:
        raise ValidationError(f"invalid {kind} status: {status}")
    validate_payload(kind, payload)
