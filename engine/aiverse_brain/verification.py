from dataclasses import dataclass, field
from enum import IntEnum
from typing import List

from .errors import ValidationError
from .models import EvidenceRef


class VerificationLevel(IntEnum):
    V0_TRIVIAL = 0
    V1_NORMAL = 1
    V2_IMPORTANT = 2
    V3_HIGH_IMPACT = 3


CRITERION_STATUSES = {"unverified", "passed", "failed", "insufficient_evidence", "not_applicable"}


@dataclass
class Criterion:
    id: str
    statement: str
    required_evidence: str = ""
    status: str = "unverified"
    evidence: List[EvidenceRef] = field(default_factory=list)

    def mark(self, status: str, evidence: List[EvidenceRef]) -> None:
        if status not in CRITERION_STATUSES:
            raise ValidationError(f"unknown criterion status: {status}")
        if status == "passed" and not evidence:
            raise ValidationError("a criterion cannot pass without evidence")
        self.status = status
        self.evidence = list(evidence)


@dataclass(frozen=True)
class VerificationFactors:
    impact: float = 0.0
    irreversibility: float = 0.0
    uncertainty: float = 0.0
    novelty: float = 0.0
    cost: float = 0.0
    sensitivity: float = 0.0
    external_side_effects: float = 0.0
    verification_difficulty: float = 0.0
    history_of_failure: float = 0.0

    def validate(self) -> None:
        for name, value in self.__dict__.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be normalized to [0,1]")


def select_level(factors: VerificationFactors, policy_floor: VerificationLevel = VerificationLevel.V0_TRIVIAL) -> VerificationLevel:
    factors.validate()
    peak = max(factors.__dict__.values())
    mean = sum(factors.__dict__.values()) / len(factors.__dict__)
    if peak >= 0.9 or (factors.irreversibility >= 0.75 and factors.impact >= 0.75) or factors.sensitivity >= 0.9:
        level = VerificationLevel.V3_HIGH_IMPACT
    elif peak >= 0.7 or mean >= 0.55:
        level = VerificationLevel.V2_IMPORTANT
    elif peak >= 0.3 or mean >= 0.2:
        level = VerificationLevel.V1_NORMAL
    else:
        level = VerificationLevel.V0_TRIVIAL
    return max(level, policy_floor)
