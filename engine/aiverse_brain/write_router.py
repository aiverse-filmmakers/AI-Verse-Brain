from enum import Enum


class WriteRoute(str, Enum):
    OS_PROFILE = "os_profile"
    OS_CONTEXT = "os_context"
    OS_DECISIONS = "os_decisions"
    MEMORY_HISTORY = "memory_history"
    OS_KNOWLEDGE = "os_knowledge"
    CAPABILITY_CANDIDATE = "capability_candidate"
    BRAIN_STATE = "brain_state"
    TRANSIENT = "transient"


_BRAIN_KINDS = {
    "intent", "practice", "gap", "opportunity", "initiative", "objective",
    "model_belief", "evaluation", "learning", "strategy_rule", "policy",
}


def classify_write(classification: str) -> WriteRoute:
    """Return the canonical owner. This function intentionally returns symbolic routes, never arbitrary paths."""
    mapping = {
        "stable_identity": WriteRoute.OS_PROFILE,
        "stable_preference": WriteRoute.OS_PROFILE,
        "current_state": WriteRoute.OS_CONTEXT,
        "settled_decision": WriteRoute.OS_DECISIONS,
        "historical_event": WriteRoute.MEMORY_HISTORY,
        "historical_experience": WriteRoute.MEMORY_HISTORY,
        "reusable_knowledge": WriteRoute.OS_KNOWLEDGE,
        "repeatable_execution": WriteRoute.CAPABILITY_CANDIDATE,
        "transient": WriteRoute.TRANSIENT,
    }
    if classification in _BRAIN_KINDS:
        return WriteRoute.BRAIN_STATE
    if classification not in mapping:
        raise ValueError(f"unknown write classification: {classification}")
    return mapping[classification]
