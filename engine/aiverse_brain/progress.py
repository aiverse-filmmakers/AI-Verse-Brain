from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .authority import AuthorityTier
from .errors import ValidationError
from .models import BrainObject, EvidenceRef, utc_now

if TYPE_CHECKING:
    from .controller import BrainController


@dataclass(frozen=True)
class AttemptObservation:
    """Observed criterion-relevant state after one attempt. Activity/tool calls alone are not progress."""

    state_token: str
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    blocked_on: Optional[str] = None


@dataclass(frozen=True)
class ProgressUpdate:
    objective_id: str
    attempt_count: int
    non_progressing_attempts: int
    meaningful_progress: bool
    status: str
    progress: str
    blocked_on: Optional[str] = None


class ProgressTracker:
    def __init__(self, controller: "BrainController"):
        self.controller = controller

    @staticmethod
    def _append_evidence(obj: BrainObject, evidence: List[EvidenceRef]) -> None:
        existing = {item.ref for item in obj.evidence_refs}
        for item in evidence:
            if item.ref not in existing:
                obj.evidence_refs.append(item)
                existing.add(item.ref)

    def record_attempt(
        self,
        scope: str,
        objective_id: str,
        observation: AttemptObservation,
        *,
        actor: str = "brain",
    ) -> ProgressUpdate:
        if not observation.state_token or not observation.state_token.strip():
            raise ValidationError("attempt state_token is required")
        obj = self.controller.store.load("objective", scope, objective_id)
        if obj.status != "RUNNING":
            raise ValidationError(f"attempts can only be recorded while objective is RUNNING, not {obj.status}")

        expected = obj.revision
        ledger = dict(obj.payload.get("progress_ledger") or {})
        prior_token = ledger.get("last_state_token")
        attempt_count = int(ledger.get("attempt_count", 0)) + 1
        previous_non_progress = int(ledger.get("non_progressing_attempts", 0))
        changed = prior_token is not None and prior_token != observation.state_token
        meaningful = changed and bool(observation.evidence_refs)

        if prior_token is None:
            non_progressing = 0  # first observation establishes a baseline
        elif meaningful:
            non_progressing = 0
        else:
            non_progressing = previous_non_progress + 1

        now = utc_now()
        ledger.update({
            "attempt_count": attempt_count,
            "non_progressing_attempts": non_progressing,
            "last_state_token": observation.state_token,
            "last_observed_at": now,
            "last_evidence_refs": [item.ref for item in observation.evidence_refs],
        })
        if meaningful:
            ledger["last_progress_at"] = now
        if observation.blocked_on:
            ledger["blocked_on"] = observation.blocked_on
        else:
            ledger.pop("blocked_on", None)

        obj.payload["progress_ledger"] = ledger
        self._append_evidence(obj, observation.evidence_refs)
        obj.updated_by = actor

        budget = obj.payload.get("budget") or {}
        max_attempts = int(budget.get("max_attempts", self.controller.policy.resources.max_objective_attempts))
        stall_threshold = int(obj.payload.get(
            "stall_threshold",
            self.controller.policy.resources.max_non_progressing_attempts_before_stall,
        ))

        target: Optional[str] = None
        blocked_on = observation.blocked_on
        if observation.blocked_on:
            obj.payload["progress"] = "blocked"
            target = "BLOCKED"
        elif attempt_count >= max_attempts:
            blocked_on = "attempt_budget_exhausted"
            obj.payload["progress"] = "blocked"
            obj.payload["blocked_on"] = blocked_on
            ledger["blocked_on"] = blocked_on
            target = "BLOCKED"
        elif non_progressing >= stall_threshold:
            obj.payload["progress"] = "stalled"
            target = "STALLED"
        else:
            obj.payload["progress"] = "progressing" if meaningful else obj.payload.get("progress", "progressing")

        saved = self.controller.store.save(obj, expected_revision=expected)
        if target:
            saved = self.controller.transition(
                "objective", scope, objective_id, target,
                source=AuthorityTier.VALIDATED_STRATEGY, actor=actor,
            )
        return ProgressUpdate(
            objective_id=objective_id,
            attempt_count=attempt_count,
            non_progressing_attempts=non_progressing,
            meaningful_progress=meaningful,
            status=saved.status,
            progress=saved.payload.get("progress", "progressing"),
            blocked_on=blocked_on,
        )
