from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .authority import AuthorityTier, assert_policy_mutation
from .cadence import Trigger, TriggerLedger
from .models import BrainObject, Scope
from .policy import BrainPolicy
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

    def __init__(self, root: str, policy: Optional[BrainPolicy] = None):
        self.layout = StorageLayout.detect(root)
        self.store = ObjectStore(self.layout)
        self.policy = policy or BrainPolicy()
        self.policy.validate()
        self.trigger_ledger = TriggerLedger(self.layout.runtime_dir)

    def create(self, kind: str, scope: str, status: str, payload: Dict[str, Any], *, source: AuthorityTier = AuthorityTier.TEMPORARY_HYPOTHESIS, actor: str = "brain") -> BrainObject:
        assert_creation(kind, status, source)
        obj = BrainObject.new(kind, scope, status, payload, created_by=actor)
        return self.store.save(obj, expected_revision=-1)

    def transition(self, kind: str, scope: str, object_id: str, target: str, *, source: AuthorityTier, actor: str) -> BrainObject:
        obj = self.store.load(kind, scope, object_id)
        assert_transition(kind, obj.status, target, source)
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
        initiatives = [o.to_dict() for o in self.store.list("initiative", scope, {"ACCEPTED", "ACTIVE", "WAITING", "BLOCKED", "STALLED", "REVIEW"})]
        objectives = [o.to_dict() for o in self.store.list("objective", scope, {"READY", "RUNNING", "WAITING", "BLOCKED", "STALLED", "VERIFYING", "INSUFFICIENT_EVIDENCE"})]
        policies = [o.to_dict() for o in self.store.list("policy", scope)]
        return Orientation(scope, goals, practices, initiatives[: self.policy.attention.max_active_initiatives], objectives, policies)

    def run_trigger(self, trigger: Trigger) -> Orientation:
        self.trigger_ledger.claim(trigger)
        try:
            result = self.orientation(trigger.scope.value)
        except Exception:
            # A claimed-but-incomplete receipt is intentionally retained for explicit recovery.
            raise
        self.trigger_ledger.complete(trigger)
        return result
