from enum import Enum


class WriteRoute(str, Enum):
    OS_PROFILE = "os_profile"
    OS_CONTEXT = "os_context"
    OS_DECISIONS = "os_decisions"
    MEMORY_HISTORY = "memory_history"
    OS_KNOWLEDGE = "os_knowledge"
    DATA_STATE = "data_state"
    CAPABILITY_CANDIDATE = "capability_candidate"
    AUTOMATION_CANDIDATE = "automation_candidate"
    BOT_CANDIDATE = "bot_candidate"
    BRAIN_STATE = "brain_state"
    TRANSIENT = "transient"


_BRAIN_KINDS = {
    "intent", "practice", "gap", "opportunity", "initiative", "objective", "goal",
    "model_belief", "evaluation", "learning", "learning_candidate", "strategy_rule", "policy",
}


def classify_write(classification: str) -> WriteRoute:
    """Return the canonical owner as a symbolic route, never an arbitrary path."""
    mapping = {
        "stable_identity": WriteRoute.OS_PROFILE,
        "stable_preference": WriteRoute.OS_PROFILE,
        "current_state": WriteRoute.OS_CONTEXT,
        "settled_decision": WriteRoute.OS_DECISIONS,
        "historical_event": WriteRoute.MEMORY_HISTORY,
        "historical_experience": WriteRoute.MEMORY_HISTORY,
        "reusable_knowledge": WriteRoute.OS_KNOWLEDGE,
        "structured_operational_state": WriteRoute.DATA_STATE,
        "repeatable_execution": WriteRoute.CAPABILITY_CANDIDATE,
        "automation_candidate": WriteRoute.AUTOMATION_CANDIDATE,
        "bot_candidate": WriteRoute.BOT_CANDIDATE,
        "transient": WriteRoute.TRANSIENT,
    }
    if classification in _BRAIN_KINDS: return WriteRoute.BRAIN_STATE
    if classification not in mapping: raise ValueError(f"unknown write classification: {classification}")
    return mapping[classification]
