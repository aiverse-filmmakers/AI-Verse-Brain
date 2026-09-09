from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class NotificationClass(str, Enum):
    INTERRUPT = "INTERRUPT"
    SURFACE = "SURFACE"
    BATCH = "BATCH"
    STORE = "STORE"
    DROP = "DROP"


@dataclass(frozen=True)
class Eligibility:
    desired_state_linked: bool = True
    scope_valid: bool = True
    permission_compatible: bool = True
    non_duplicate: bool = True
    evidence_fresh_enough: bool = True
    minimum_confidence_met: bool = True
    cooldown_clear: bool = True
    hard_boundary_clear: bool = True

    def reasons(self) -> List[str]:
        names = {
            "desired_state_linked": self.desired_state_linked,
            "scope_valid": self.scope_valid,
            "permission_compatible": self.permission_compatible,
            "non_duplicate": self.non_duplicate,
            "evidence_fresh_enough": self.evidence_fresh_enough,
            "minimum_confidence_met": self.minimum_confidence_met,
            "cooldown_clear": self.cooldown_clear,
            "hard_boundary_clear": self.hard_boundary_clear,
        }
        return [name for name, passed in names.items() if not passed]


@dataclass(frozen=True)
class ScoreComponents:
    goal_alignment: float
    expected_impact: float
    urgency: float
    confidence: float
    strategic_leverage: float
    readiness_4c: float
    reversibility: float
    effort_cost: float
    attention_cost: float
    risk: float
    opportunity_cost: float

    def validate(self) -> None:
        for name, value in self.__dict__.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be normalized to [0,1]")


DEFAULT_WEIGHTS = {
    "goal_alignment": 1.8,
    "expected_impact": 1.6,
    "urgency": 1.0,
    "confidence": 1.2,
    "strategic_leverage": 1.2,
    "readiness_4c": 0.9,
    "reversibility": 0.5,
    "effort_cost": 0.8,
    "attention_cost": 0.9,
    "risk": 1.3,
    "opportunity_cost": 0.7,
}


@dataclass(frozen=True)
class RankResult:
    eligible: bool
    score: Optional[float]
    gate_failures: List[str]
    notification: NotificationClass


def rank(eligibility: Eligibility, components: ScoreComponents, *, minimum_interrupt: float = 0.82, minimum_surface: float = 0.62) -> RankResult:
    failures = eligibility.reasons()
    if failures:
        return RankResult(False, None, failures, NotificationClass.DROP)
    components.validate()
    positive = (
        components.goal_alignment * DEFAULT_WEIGHTS["goal_alignment"] +
        components.expected_impact * DEFAULT_WEIGHTS["expected_impact"] +
        components.urgency * DEFAULT_WEIGHTS["urgency"] +
        components.confidence * DEFAULT_WEIGHTS["confidence"] +
        components.strategic_leverage * DEFAULT_WEIGHTS["strategic_leverage"] +
        components.readiness_4c * DEFAULT_WEIGHTS["readiness_4c"] +
        components.reversibility * DEFAULT_WEIGHTS["reversibility"]
    )
    negative = (
        components.effort_cost * DEFAULT_WEIGHTS["effort_cost"] +
        components.attention_cost * DEFAULT_WEIGHTS["attention_cost"] +
        components.risk * DEFAULT_WEIGHTS["risk"] +
        components.opportunity_cost * DEFAULT_WEIGHTS["opportunity_cost"]
    )
    max_positive = sum(DEFAULT_WEIGHTS[k] for k in ("goal_alignment", "expected_impact", "urgency", "confidence", "strategic_leverage", "readiness_4c", "reversibility"))
    max_negative = sum(DEFAULT_WEIGHTS[k] for k in ("effort_cost", "attention_cost", "risk", "opportunity_cost"))
    score = (positive + (max_negative - negative)) / (max_positive + max_negative)
    score = max(0.0, min(1.0, score))
    if score >= minimum_interrupt and components.urgency >= 0.75 and components.confidence >= 0.7:
        notification = NotificationClass.INTERRUPT
    elif score >= minimum_surface:
        notification = NotificationClass.SURFACE
    elif score >= minimum_surface * 0.75:
        notification = NotificationClass.BATCH
    else:
        notification = NotificationClass.STORE
    return RankResult(True, score, [], notification)
