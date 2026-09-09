from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .attention import AttentionLedger
from .authority import AuthorityTier, assert_policy_mutation
from .cadence import Trigger, TriggerLedger
from .direction import DirectionService
from .errors import PolicyViolation, ValidationError
from .evaluator import EvaluationService
from .freshness import FreshnessService
from .learning import LearningService, assert_learning_transition, assert_strategy_activation
from .models import BrainObject, EvidenceRef, Scope
from .policy import BrainPolicy
from .progress import ProgressTracker
from .state_machine import assert_creation, assert_transition
from .storage import ObjectStore, StorageLayout


@dataclass
class Orientation:
    scope: str
    confirmed_goals: List[Dict[str, Any]]
    active_practices: List[Dict[str, Any]]
    active_initiatives: List[Dict[str, Any]]
    current_objectives: List[Dict[str, Any]]
    hard_policies: List[Dict[str, Any]]


class BrainController:
    """Deterministic state/control core. It does not perform model reasoning or external side effects."""

    ACTIVE_INITIATIVE_STATES = {"ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "REVIEW"}
    ACTIVE_OBJECTIVE_STATES = {"READY", "RUNNING", "WAITING", "BLOCKED", "STALLED", "VERIFYING", "INSUFFICIENT_EVIDENCE"}

    def __init__(self, root: str, policy: Optional[BrainPolicy] = None):
        self.layout = StorageLayout.detect(root)
        self.store = ObjectStore(self.layout)
        self.policy = policy or BrainPolicy()
        self.policy.validate()
        self.trigger_ledger = TriggerLedger(self.layout.runtime_dir)
        self.attention = AttentionLedger(self.layout.runtime_dir)
        self.direction = DirectionService(self)
        self.progress = ProgressTracker(self)
        self.evaluator = EvaluationService(self)
        self.freshness = FreshnessService(self)
        self.learning = LearningService(self)

    def create(
        self,
        kind: str,
        scope: str,
        status: str,
        payload: Dict[str, Any],
        *,
        source: AuthorityTier = AuthorityTier.TEMPORARY_HYPOTHESIS,
        actor: str = "brain",
        source_refs: Optional[List[str]] = None,
        evidence_refs: Optional[List[EvidenceRef]] = None,
        supersedes: Optional[str] = None,
    ) -> BrainObject:
        assert_creation(kind, status, source)
        obj = BrainObject.new(kind, scope, status, payload, created_by=actor)
        obj.source_refs = list(source_refs or [])
        obj.evidence_refs = list(evidence_refs or [])
        obj.supersedes = supersedes
        return self.store.save(obj, expected_revision=-1)

    def _assert_initiative_capacity(self, scope: str, *, exclude_id: Optional[str] = None) -> None:
        active = [
            item for item in self.store.list("initiative", scope, self.ACTIVE_INITIATIVE_STATES)
            if item.id != exclude_id
        ]
        if len(active) >= self.policy.attention.max_active_initiatives:
            raise PolicyViolation(f"active initiative WIP cap reached ({self.policy.attention.max_active_initiatives})")

    def _assert_objective_capacity(self, scope: str, *, exclude_id: Optional[str] = None) -> None:
        active = [
            item for item in self.store.list("objective", scope, self.ACTIVE_OBJECTIVE_STATES)
            if item.id != exclude_id
        ]
        if len(active) >= self.policy.resources.max_parallel_objectives:
            raise PolicyViolation(f"parallel objective cap reached ({self.policy.resources.max_parallel_objectives})")

    @staticmethod
    def _assert_objective_passable(obj: BrainObject) -> None:
        criteria = obj.payload.get("criteria", [])
        if not criteria:
            raise ValidationError("objective cannot pass without criteria")
        invalid = [c.get("id", "?") for c in criteria if c.get("status") not in {"passed", "not_applicable"}]
        if invalid:
            raise ValidationError("objective cannot pass while criteria remain unverified/failed: " + ", ".join(invalid))
        passed = [c for c in criteria if c.get("status") == "passed"]
        if not passed:
            raise ValidationError("objective cannot pass without at least one passed criterion")
        if any(not c.get("evidence_refs") for c in passed):
            raise ValidationError("every passed criterion requires evidence_refs")

    @staticmethod
    def _assert_initiative_completable(obj: BrainObject) -> None:
        if not obj.payload.get("evaluation_refs"):
            raise ValidationError("initiative completion requires evaluation_refs")

    def transition(self, kind: str, scope: str, object_id: str, target: str, *, source: AuthorityTier, actor: str) -> BrainObject:
        obj = self.store.load(kind, scope, object_id)
        assert_transition(kind, obj.status, target, source)
        if kind == "initiative" and target in {"ACCEPTED", "ACTIVE"} and obj.status not in self.ACTIVE_INITIATIVE_STATES:
            self._assert_initiative_capacity(scope, exclude_id=obj.id)
        if kind == "objective" and target == "READY" and obj.status not in self.ACTIVE_OBJECTIVE_STATES:
            self._assert_objective_capacity(scope, exclude_id=obj.id)
        if kind == "objective" and target == "PASSED":
            self._assert_objective_passable(obj)
        if kind == "initiative" and target == "COMPLETED":
            self._assert_initiative_completable(obj)
        if kind == "learning":
            assert_learning_transition(obj, target, source)
        if kind == "strategy_rule" and target == "ACTIVE":
            assert_strategy_activation(obj, source, self.policy)
        expected = obj.revision
        obj.status = target
        obj.updated_by = actor
        return self.store.save(obj, expected_revision=expected)

    def update_policy(self, object_id: str, scope: str, payload: Dict[str, Any], *, source: AuthorityTier, actor: str) -> BrainObject:
        assert_policy_mutation(source)
        obj = self.store.load("policy", scope, object_id)
        expected = obj.revision
        obj.payload = dict(payload)
        obj.updated_by = actor
        return self.store.save(obj, expected_revision=expected)

    def orientation(self, scope: str) -> Orientation:
        Scope(scope)
        goals = [o.to_dict() for o in self.store.list("intent", scope, {"CONFIRMED", "ACTIVE"}) if o.payload.get("subtype") in {"goal", "desired_state"}]
        practices = [o.to_dict() for o in self.store.list("practice", scope, {"ACTIVE"})]
        initiatives = [o.to_dict() for o in self.store.list("initiative", scope, self.ACTIVE_INITIATIVE_STATES)]
        objectives = [o.to_dict() for o in self.store.list("objective", scope, self.ACTIVE_OBJECTIVE_STATES)]
        policies = [o.to_dict() for o in self.store.list("policy", scope)]
        return Orientation(scope, goals, practices, initiatives[: self.policy.attention.max_active_initiatives], objectives, policies)

    def run_trigger(self, trigger: Trigger) -> Orientation:
        self.trigger_ledger.claim(trigger)
        try:
            result = self.orientation(trigger.scope.value)
        except Exception:
            # Claimed receipt remains for explicit stale-claim recovery. Do not auto-replay uncertain work.
            raise
        self.trigger_ledger.complete(trigger)
        return result
