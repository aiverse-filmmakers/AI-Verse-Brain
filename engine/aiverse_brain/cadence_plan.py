from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Optional

from .models import Scope
from .policy import BrainPolicy, ProactivityLevel


@dataclass(frozen=True)
class CadenceRequest:
    trigger_type: str
    scope: str
    delivery: str
    interval_seconds: Optional[int]
    reason: str

    def to_dict(self):
        return {
            "trigger_type": self.trigger_type,
            "scope": self.scope,
            "delivery": self.delivery,
            "interval_seconds": self.interval_seconds,
            "reason": self.reason,
        }


def plan_cadence(policy: BrainPolicy, scope: str) -> List[CadenceRequest]:
    """Return host scheduling requests. Brain never runs the scheduler itself."""
    Scope(scope)
    policy.validate()
    requests = [
        CadenceRequest("session_start", scope, "event_hook", None, "orient before interaction"),
        CadenceRequest("session_end", scope, "event_hook", None, "capture bounded reflection candidates after interaction"),
    ]
    if policy.proactivity <= ProactivityLevel.P1_OBSERVANT:
        return requests

    ticks = max(1, int(policy.resources.max_background_ticks_per_day))
    minimum_interval = max(3600, int(math.ceil(86400 / ticks)))
    requests.extend([
        CadenceRequest(
            "scheduled_orientation", scope, "interval", minimum_interval,
            "bounded ambient orientation; host may schedule less frequently",
        ),
        CadenceRequest(
            "scheduled_review", scope, "interval", 7 * 86400,
            "strategic review of goals, gaps, initiatives, stale beliefs, and learning candidates",
        ),
    ])
    return requests
