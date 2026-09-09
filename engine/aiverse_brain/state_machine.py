from typing import Dict, Set

from .authority import AuthorityTier, assert_goal_confirmation
from .errors import TransitionError

_TRANSITIONS: Dict[str, Dict[str, Set[str]]] = {
    "intent": {
        "DRAFT": {"PROPOSED"},
        "PROPOSED": {"CONFIRMED", "ABANDONED"},
        "CONFIRMED": {"ACTIVE", "ABANDONED", "SUPERSEDED"},
        "ACTIVE": {"PAUSED", "ACHIEVED", "ABANDONED", "SUPERSEDED"},
        "PAUSED": {"ACTIVE", "ABANDONED", "SUPERSEDED"},
        "ACHIEVED": set(), "ABANDONED": set(), "SUPERSEDED": set(),
    },
    "practice": {
        "DRAFT": {"PROPOSED"},
        "PROPOSED": {"CONFIRMED", "RETIRED"},
        "CONFIRMED": {"ACTIVE", "RETIRED"},
        "ACTIVE": {"PAUSED", "RETIRED"},
        "PAUSED": {"ACTIVE", "RETIRED"},
        "RETIRED": set(),
    },
    "opportunity": {
        "DETECTED": {"DISMISSED", "EXPIRED", "WATCHING", "QUALIFIED"},
        "WATCHING": {"DISMISSED", "EXPIRED", "QUALIFIED"},
        "QUALIFIED": {"PROPOSED_INITIATIVE", "DISMISSED", "EXPIRED"},
        "PROPOSED_INITIATIVE": set(), "DISMISSED": set(), "EXPIRED": set(),
    },
    "initiative": {
        "DISCOVERED": {"PROPOSED"},
        "PROPOSED": {"REJECTED", "DEFERRED", "ACCEPTED"},
        "DEFERRED": {"PROPOSED", "REJECTED"},
        "ACCEPTED": {"ACTIVE", "PAUSED", "ABANDONED"},
        "ACTIVE": {"WAITING", "BLOCKED", "STALLED", "PAUSED", "REVIEW"},
        "WAITING": {"ACTIVE", "BLOCKED", "PAUSED", "REVIEW"},
        "BLOCKED": {"ACTIVE", "PAUSED", "ABANDONED", "REVIEW"},
        "STALLED": {"ACTIVE", "PAUSED", "ABANDONED", "REVIEW"},
        "PAUSED": {"ACTIVE", "ABANDONED", "SUPERSEDED"},
        "REVIEW": {"ACTIVE", "COMPLETED", "ABANDONED", "SUPERSEDED"},
        "REJECTED": set(), "COMPLETED": set(), "ABANDONED": set(), "SUPERSEDED": set(),
    },
    "objective": {
        "QUEUED": {"READY", "CANCELLED", "SUPERSEDED"},
        "READY": {"RUNNING", "CANCELLED", "SUPERSEDED"},
        "RUNNING": {"WAITING", "BLOCKED", "STALLED", "VERIFYING", "CANCELLED", "SUPERSEDED"},
        "WAITING": {"RUNNING", "BLOCKED", "CANCELLED", "SUPERSEDED"},
        "BLOCKED": {"READY", "RUNNING", "CANCELLED", "SUPERSEDED"},
        "STALLED": {"READY", "RUNNING", "CANCELLED", "SUPERSEDED"},
        "VERIFYING": {"PASSED", "FAILED", "INSUFFICIENT_EVIDENCE", "RUNNING"},
        "INSUFFICIENT_EVIDENCE": {"RUNNING", "VERIFYING", "CANCELLED"},
        "FAILED": {"READY", "CANCELLED", "SUPERSEDED"},
        "PASSED": set(), "CANCELLED": set(), "SUPERSEDED": set(),
    },
    "learning": {
        "OBSERVATION": {"HYPOTHESIS"},
        "HYPOTHESIS": {"PATTERN", "REJECTED"},
        "PATTERN": {"REFLECTION", "REJECTED"},
        "REFLECTION": {"VALIDATED_LEARNING", "REJECTED"},
        "VALIDATED_LEARNING": {"STRATEGY_CANDIDATE"},
        "STRATEGY_CANDIDATE": {"PROMOTED", "REJECTED"},
        "PROMOTED": set(), "REJECTED": set(),
    },
    "strategy_rule": {
        "CANDIDATE": {"ACTIVE", "REJECTED"},
        "ACTIVE": {"RETIRED", "ROLLED_BACK"},
        "RETIRED": {"ACTIVE"},
        "ROLLED_BACK": set(), "REJECTED": set(),
    },
}


def allowed_transitions(kind: str, status: str) -> Set[str]:
    return set(_TRANSITIONS.get(kind, {}).get(status, set()))


def assert_transition(kind: str, current: str, target: str, source: AuthorityTier) -> None:
    allowed = allowed_transitions(kind, current)
    if target not in allowed:
        raise TransitionError(f"invalid {kind} transition: {current} -> {target}")
    if kind in {"intent", "practice"} and current == "PROPOSED" and target == "CONFIRMED":
        assert_goal_confirmation(source)
